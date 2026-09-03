"""Import real Skool communities from public discovery search pages.

Only imports slugs that appear on Skool's own discovery HTML/JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.invites import _SKOOL_BLOCKED, classify_invite_url  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_slugs(html: str) -> set[str]:
    slugs: set[str] = set()
    for pattern in (
        r"skool\.com/([a-z0-9][a-z0-9_-]{1,40})",
        r'"slug"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"',
        r'"name"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"',
    ):
        for m in re.finditer(pattern, html, re.I):
            slugs.add(m.group(1).lower())
    start = html.find('id="__NEXT_DATA__"')
    if start >= 0:
        gt = html.find(">", start)
        end = html.find("</script>", gt)
        try:
            blob = json.dumps(json.loads(html[gt + 1 : end]))
            for m in re.finditer(r'"(?:slug|name)"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', blob, re.I):
                slugs.add(m.group(1).lower())
        except Exception:
            pass
    return {
        s
        for s in slugs
        if s not in _SKOOL_BLOCKED and s not in {"discovery", "academy", "agent", "amanda", "amharic"}
    }


def load_queries(limit: int) -> list[str]:
    niches = [
        line.strip().replace("-", " ")
        for line in (ROOT / "data" / "niches_usa.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    extras = [
        "ai",
        "marketing",
        "fitness",
        "business",
        "crypto",
        "coaching",
        "agency",
        "saas",
        "trading",
        "dropshipping",
        "youtube",
        "instagram",
        "ecommerce",
        "copywriting",
        "sales",
        "investing",
        "real estate",
        "health",
        "mindset",
        "productivity",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for q in extras + niches:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.7)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))}

    queries = load_queries(args.queries)
    found: dict[str, str] = {}
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        # Always include the main discovery feed.
        urls = ["https://www.skool.com/discovery"] + [
            f"https://www.skool.com/discovery?q={quote_plus(q)}" for q in queries
        ]
        for idx, url in enumerate(urls, start=1):
            try:
                html = client.get(url).text
            except Exception as exc:  # noqa: BLE001
                print(f"fetch_error {url} {type(exc).__name__}", flush=True)
                continue
            slugs = extract_slugs(html)
            for slug in slugs:
                found.setdefault(slug, url)
            print(f"{idx}/{len(urls)} slugs_page={len(slugs)} unique={len(found)}", flush=True)
            time.sleep(args.delay)

    rows = []
    for slug, source_url in found.items():
        invite = classify_invite_url(f"https://www.skool.com/{slug}")
        if not invite:
            continue
        norm = normalize_url(invite.url)
        if norm.is_blocked or norm.canonical_key in existing:
            continue
        existing.add(norm.canonical_key)
        rows.append(
            {
                "id": str(uuid4()),
                "canonical_key": norm.canonical_key,
                "canonical_domain": norm.canonical_domain,
                "platform": "skool",
                "platform_id": norm.platform_id,
                "website": invite.url,
                "name": slug,
                "niche": None,
                "audience": None,
                "geo": "USA",
                "join_url": invite.url,
                "source_queries": json.dumps(["skool:discovery"]),
                "raw_signals": json.dumps(
                    {
                        "source": "skool_discovery",
                        "discovery_url": source_url,
                        "real_directory": True,
                    }
                ),
            }
        )

    inserted = 0
    sql = text(
        """
        INSERT INTO community_scanner (
          id, canonical_key, canonical_domain, platform, platform_id,
          website, name, niche, audience, geo, join_url,
          contacts, access_status, value_score, value_tier,
          relevance_score, source_queries, raw_signals, sync_status
        ) VALUES (
          :id, :canonical_key, :canonical_domain, :platform, :platform_id,
          :website, :name, :niche, :audience, :geo, :join_url,
          '{}'::jsonb, 'join', 35, 'low',
          0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
        )
        ON CONFLICT (canonical_key) DO NOTHING
        """
    )
    with engine.begin() as conn:
        for i in range(0, len(rows), 500):
            chunk = rows[i : i + 500]
            result = conn.execute(sql, chunk)
            inserted += int(result.rowcount or 0)
            print(f"insert_progress {inserted}/{len(rows)}", flush=True)
        total = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
        by_plat = conn.execute(
            text("SELECT platform, count(*) n FROM community_scanner GROUP BY 1 ORDER BY n DESC")
        ).fetchall()
    print(f"done found={len(found)} new_rows={len(rows)} inserted={inserted} total={total}", flush=True)
    for p, n in by_plat:
        print(f"  {p}={n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
