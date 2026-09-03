"""Import public discussion communities from catalog pages and old discoveries.

This importer never fabricates identifiers. It accepts only canonical URL
shapes for public Reddit, GitHub Discussions, Stack Exchange Chat, Matrix
directories, Zulip, and obvious Discourse/Mattermost community pages.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.content_filter import is_adult_community  # noqa: E402
from community_scanner.language_filter import is_russian_community  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarmrSocialCommunityImporter/1.0)"}
CATALOGS = (
    "https://zulip.com/communities/",
    "https://matrixrooms.info/",
    "https://matrix.org/homeserver/room-directory/",
    "https://chat.stackexchange.com/rooms",
    "https://www.reddit.com/subreddits/",
)
SUPPORTED = {
    "reddit",
    "discourse",
    "matrix",
    "geneva",
    "mattermost",
    "zulip",
    "github",
    "stackexchange",
    "disqus",
}


def platform_for(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.split("/") if p]
    if host in {"reddit.com", "old.reddit.com"} and len(parts) >= 2 and parts[0].lower() == "r":
        return "reddit", parts[1]
    if host == "github.com" and len(parts) >= 3 and parts[2].lower() == "discussions":
        return "github", "/".join(parts[:2])
    if host == "chat.stackexchange.com" and len(parts) >= 2 and parts[0] == "rooms":
        return "stackexchange", parts[1]
    if host in {"matrixrooms.info", "matrix.to"} and parts:
        return "matrix", "/".join(parts[:3])
    if host == "zulip.com" and parts and parts[0] == "communities":
        return "zulip", "/".join(parts[:3])
    if host.endswith("zulipchat.com"):
        return "zulip", host
    if host == "geneva.com":
        return "geneva", "/".join(parts[:3]) or host
    if host == "mattermost.com" or host.endswith(".mattermost.com"):
        return "mattermost", "/".join(parts[:3]) or host
    if host == "disqus.com" and parts:
        return "disqus", "/".join(parts[:3])
    # Public forum/community pages commonly expose Discourse's /t/ routes.
    if parts and (parts[0].lower() in {"t", "c", "categories", "community"}):
        if any(token in host for token in ("forum", "community", "discourse")):
            return "discourse", "/".join(parts[:4])
    return None


def candidate(url: str, title: str, source: str) -> dict | None:
    match = platform_for(url)
    if not match:
        return None
    platform, platform_id = match
    if platform not in SUPPORTED:
        return None
    if is_adult_community(name=title, url=url, platform_id=platform_id):
        return None
    if is_russian_community(name=title, url=url, platform_id=platform_id):
        return None
    norm = normalize_url(url)
    if not norm.canonical_key or norm.is_blocked:
        return None
    return {
        "id": str(uuid4()),
        "canonical_key": f"{platform}:{platform_id.lower()}",
        "canonical_domain": norm.canonical_domain,
        "platform": platform,
        "platform_id": platform_id,
        "website": url,
        "name": (title or platform_id)[:500],
        "niche": None,
        "audience": None,
        "geo": "USA",
        "join_url": url,
        "source_queries": json.dumps([f"public_catalog:{source}"]),
        "raw_signals": json.dumps({"source": source, "public_catalog": True}),
    }


def crawl_catalog(url: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    try:
        with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            response = client.get(url)
            html = response.text or ""
    except Exception:
        return out
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    raw_urls = [urljoin(url, h).split("#")[0] for h in hrefs]
    raw_urls.extend(
        re.findall(
            r"https?://(?:www\.)?(?:reddit\\.com/r/|github\\.com/[^/]+/[^/]+/discussions|"
            r"chat\\.stackexchange\\.com/rooms/|matrixrooms\\.info/room/|"
            r"[a-z0-9-]+\\.zulipchat\\.com)",
            html,
            re.I,
        )
    )
    title_match = re.search(r"<title[^>]*>([^<]+)", html, re.I)
    title = title_match.group(1).strip() if title_match else url
    for raw in raw_urls:
        if raw.lower() in seen:
            continue
        seen.add(raw.lower())
        row = candidate(raw, title, url)
        if row:
            out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        existing = {r[0] for r in conn.execute(text("SELECT canonical_key FROM community_scanner"))}

    rows: list[dict] = []
    with engine.connect() as conn:
        discovery = conn.execute(
            text(
                """
                SELECT url, coalesce(title, ''), 'discovery_results'
                FROM discovery_results
                WHERE url IS NOT NULL
                """
            )
        ).fetchall()
    for url, title, source in discovery:
        row = candidate(str(url), str(title), source)
        if row:
            rows.append(row)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(crawl_catalog, url): url for url in CATALOGS}
        for future in as_completed(futures):
            source = futures[future]
            try:
                found = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"source_error {source} {type(exc).__name__}", flush=True)
                continue
            print(f"source_done {source} candidates={len(found)}", flush=True)
            rows.extend(found)

    unique = []
    for row in rows:
        if row["canonical_key"] in existing:
            continue
        existing.add(row["canonical_key"])
        unique.append(row)

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
          '{}'::jsonb, 'join', 35, 'medium',
          0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
        )
        ON CONFLICT (canonical_key) DO NOTHING
        """
    )
    inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(unique), 500):
            inserted += int(conn.execute(sql, unique[i : i + 500]).rowcount or 0)
        total = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
        by_platform = conn.execute(
            text("SELECT platform, count(*) FROM community_scanner GROUP BY 1 ORDER BY 2 DESC")
        ).fetchall()
    print(f"done candidates={len(rows)} unique_new={len(unique)} inserted={inserted} total={total}")
    for platform, count in by_platform:
        print(f"  {platform}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
