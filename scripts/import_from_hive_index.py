"""Import real communities from The Hive Index directory.

Supports Slack, Skool, Circle, WhatsApp, Facebook Groups, LinkedIn Groups,
and Telegram groups (channels + Russian language are rejected).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.content_filter import is_adult_community  # noqa: E402
from community_scanner.invites import (  # noqa: E402
    ACTIVE_HARVEST_PLATFORMS,
    classify_invite_url,
    classify_telegram_page_kind,
    find_all_invites_in_text,
)
from community_scanner.language_filter import is_russian_community  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

PLATFORM_PAGES = [
    "https://thehiveindex.com/platforms/slack/",
    "https://thehiveindex.com/platforms/skool/",
    "https://thehiveindex.com/platforms/circle/",
    "https://thehiveindex.com/platforms/whatsapp/",
    "https://thehiveindex.com/platforms/facebook/",
    "https://thehiveindex.com/platforms/linkedin/",
    "https://thehiveindex.com/platforms/telegram/",
]

TOPIC_PAGES = [
    "https://thehiveindex.com/topics/entrepreneurship/",
    "https://thehiveindex.com/topics/software-development/",
    "https://thehiveindex.com/topics/marketing/",
    "https://thehiveindex.com/topics/investing/",
    "https://thehiveindex.com/topics/fitness/",
    "https://thehiveindex.com/topics/crypto/",
    "https://thehiveindex.com/topics/design/",
    "https://thehiveindex.com/topics/product-management/",
    "https://thehiveindex.com/topics/sales/",
    "https://thehiveindex.com/topics/artificial-intelligence/",
]


def clean_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in {"ref", "utm_source", "utm_medium", "utm_campaign"}]
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def extract_community_pages(html: str, base: str) -> set[str]:
    out: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', html):
        abs_url = urljoin(base, href).split("#")[0]
        path = urlparse(abs_url).path.rstrip("/")
        if path.startswith("/communities/") and path.count("/") >= 2:
            out.add(abs_url if abs_url.endswith("/") else abs_url + "/")
    return out


def extract_invites(html: str) -> list:
    # Decode common HTML entities before invite scan.
    blob = (
        html.replace("&amp;", "&")
        .replace("&#x2F;", "/")
        .replace("&#47;", "/")
    )
    return find_all_invites_in_text(blob, limit=50)


def telegram_is_allowed_group(url: str, client: httpx.Client) -> tuple[bool, str, str | None]:
    try:
        resp = client.get(url)
    except Exception as exc:  # noqa: BLE001
        return False, f"fetch_error:{type(exc).__name__}", None
    if resp.status_code >= 400:
        return False, f"http_{resp.status_code}", None
    html = resp.text or ""
    name = None
    m = re.search(r'class="tgme_page_title[^"]*"[^>]*>\s*<span[^>]*>([^<]+)', html, re.I)
    if m:
        name = m.group(1).strip()
    if not name:
        m = re.search(r"<title>([^<]+)</title>", html, re.I)
        if m:
            name = re.sub(r"\s*[|\-–].*$", "", m.group(1)).strip() or None
    if is_russian_community(name=name, url=url, html=html[:8000]):
        return False, "russian", name
    kind = classify_telegram_page_kind(html)
    if kind == "channel":
        return False, "channel", name
    if kind == "unknown" and "/+" not in url and "joinchat" not in url.lower():
        # Public username without clear group markers — skip to avoid channels.
        return False, "unknown_kind", name
    return True, kind, name


def row_from_invite(invite_url: str, *, name: str | None, source_page: str) -> dict | None:
    invite = classify_invite_url(clean_url(invite_url))
    if not invite or invite.platform not in ACTIVE_HARVEST_PLATFORMS:
        return None
    norm = normalize_url(invite.url)
    if norm.is_blocked or not norm.canonical_key:
        return None
    if is_adult_community(name=name, url=invite.url, platform_id=norm.platform_id):
        return None
    if is_russian_community(name=name, url=invite.url, platform_id=norm.platform_id, source_url=source_page):
        return None
    return {
        "id": str(uuid4()),
        "canonical_key": norm.canonical_key,
        "canonical_domain": norm.canonical_domain,
        "platform": invite.platform,
        "platform_id": norm.platform_id,
        "website": invite.url,
        "name": (name or invite.url)[:500],
        "niche": None,
        "audience": None,
        "geo": "USA",
        "join_url": invite.url,
        "source_queries": json.dumps(["hiveindex"]),
        "raw_signals": json.dumps(
            {
                "source": "hive_index",
                "hive_page": source_page,
                "invite_rule": invite.rule,
            }
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit-pages", type=int, default=0)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        existing = {r[0] for r in conn.execute(text("SELECT canonical_key FROM community_scanner"))}

    listing_urls = PLATFORM_PAGES + TOPIC_PAGES
    community_pages: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        for idx, url in enumerate(listing_urls, start=1):
            try:
                html = client.get(url).text
            except Exception as exc:  # noqa: BLE001
                print(f"listing_error {url} {type(exc).__name__}", flush=True)
                continue
            found = extract_community_pages(html, url)
            community_pages |= found
            print(f"listing {idx}/{len(listing_urls)} {url} pages=+{len(found)} total={len(community_pages)}", flush=True)
            time.sleep(args.delay)

    pages = sorted(community_pages)
    if args.limit_pages:
        pages = pages[: args.limit_pages]
    print(f"community_pages_to_fetch={len(pages)}", flush=True)

    pending: list[dict] = []
    inserted = 0
    skipped = 0
    reasons: dict[str, int] = {}

    def flush() -> None:
        nonlocal pending, inserted
        if not pending:
            return
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
              '{}'::jsonb, 'join', 40, 'medium',
              0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
            )
            ON CONFLICT (canonical_key) DO NOTHING
            """
        )
        with engine.begin() as conn:
            result = conn.execute(sql, pending)
            inserted += int(result.rowcount or 0)
        pending.clear()

    def process_page(page: str) -> list[dict]:
        local: list[dict] = []
        with httpx.Client(headers=HEADERS, timeout=25.0, follow_redirects=True) as client:
            try:
                html = client.get(page).text
            except Exception:
                return local
            title = None
            m = re.search(r"<title>([^<]+)</title>", html, re.I)
            if m:
                title = re.sub(r"\s*[|\-–].*$", "", m.group(1)).strip() or None
            invites = extract_invites(html)
            for invite in invites:
                if invite.platform == "telegram":
                    ok, reason, tg_name = telegram_is_allowed_group(invite.url, client)
                    if not ok:
                        reasons[reason] = reasons.get(reason, 0) + 1
                        continue
                    name = tg_name or title
                else:
                    name = title
                row = row_from_invite(invite.url, name=name, source_page=page)
                if row:
                    local.append(row)
        return local

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(process_page, page) for page in pages]
        for fut in as_completed(futures):
            rows = fut.result()
            done += 1
            for row in rows:
                if row["canonical_key"] in existing:
                    skipped += 1
                    continue
                existing.add(row["canonical_key"])
                pending.append(row)
            if len(pending) >= 200:
                flush()
            if done % 50 == 0 or done == len(pages):
                print(
                    f"progress {done}/{len(pages)} pending={len(pending)} "
                    f"inserted={inserted} skipped={skipped}",
                    flush=True,
                )

    flush()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
        by_plat = conn.execute(
            text("SELECT platform, count(*) n FROM community_scanner GROUP BY 1 ORDER BY n DESC")
        ).fetchall()
    print(f"done inserted={inserted} skipped={skipped} total={total}", flush=True)
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  reject_{k}={v}", flush=True)
    for p, n in by_plat:
        print(f"  {p}={n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
