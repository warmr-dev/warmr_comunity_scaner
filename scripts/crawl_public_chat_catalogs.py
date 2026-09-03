"""Crawl public catalog pages and import only extracted chat/community URLs.

No URLs are generated. Telegram entries are kept only when their public page
indicates a group (members/group) and does not contain Cyrillic content.
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
from community_scanner.invites import (  # noqa: E402
    classify_invite_url,
    classify_telegram_page_kind,
    find_all_invites_in_text,
)
from community_scanner.language_filter import is_russian_community  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarmrPublicCatalogCrawler/1.0)"}
SEEDS = (
    "https://www.groupjoin.link/whatsapp-groups",
    "https://www.groupjoin.link/html-sitemap",
    "https://telekit.link/telegram-groups",
    "https://letstg.com/en/home",
    "https://discover.circle.so/",
    "https://thehiveindex.com/platforms/circle/",
    "https://thehiveindex.com/platforms/slack/",
    "https://thehiveindex.com/platforms/whatsapp/",
)
ALLOWED = {"slack", "skool", "whatsapp", "circle", "facebook", "linkedin", "telegram"}
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")


def same_catalog(url: str, seed: str) -> bool:
    return urlparse(url).netloc.lower().endswith(urlparse(seed).netloc.lower())


def extract_links(html: str, base: str) -> tuple[set[str], list]:
    links = {
        urljoin(base, href).split("#")[0]
        for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    }
    invites = find_all_invites_in_text(
        html.replace("&amp;", "&").replace("&#x2F;", "/").replace("&#47;", "/"),
        limit=10_000,
    )
    return links, invites


def inspect_telegram(url: str, client: httpx.Client) -> bool:
    if "/+" in url or "joinchat" in url.lower():
        return True
    try:
        response = client.get(url)
    except Exception:
        return False
    if response.status_code >= 400:
        return False
    html = response.text or ""
    if CYRILLIC_RE.search(html[:20_000]):
        return False
    return classify_telegram_page_kind(html) == "group"


def row_for(url: str, title: str, source: str, client: httpx.Client) -> dict | None:
    invite = classify_invite_url(url)
    if not invite or invite.platform not in ALLOWED:
        return None
    if invite.platform == "telegram" and not inspect_telegram(invite.url, client):
        return None
    norm = normalize_url(invite.url)
    if is_adult_community(name=title, url=invite.url, platform_id=norm.platform_id):
        return None
    if is_russian_community(name=title, url=invite.url, platform_id=norm.platform_id):
        return None
    if norm.is_blocked or not norm.canonical_key:
        return None
    return {
        "id": str(uuid4()),
        "canonical_key": norm.canonical_key,
        "canonical_domain": norm.canonical_domain,
        "platform": invite.platform,
        "platform_id": norm.platform_id,
        "website": invite.url,
        "name": (title or invite.url)[:500],
        "niche": None,
        "audience": None,
        "geo": "USA",
        "join_url": invite.url,
        "source_queries": json.dumps([f"catalog:{source}"]),
        "raw_signals": json.dumps(
            {"source": source, "catalog_url": source, "direct_url": True}
        ),
    }


def crawl_seed(seed: str, max_pages: int) -> list[dict]:
    pages = [seed]
    seen_pages = {seed}
    candidates: list[dict] = []
    seen_urls: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=20.0, follow_redirects=True) as client:
        while pages and len(seen_pages) <= max_pages:
            page = pages.pop(0)
            try:
                response = client.get(page)
                html = response.text or ""
            except Exception:
                continue
            title_match = re.search(r"<title[^>]*>([^<]+)", html, re.I)
            title = title_match.group(1).strip() if title_match else page
            links, invites = extract_links(html, page)
            for invite in invites:
                if invite.url.lower().rstrip("/") not in seen_urls:
                    seen_urls.add(invite.url.lower().rstrip("/"))
                    row = row_for(invite.url, title, seed, client)
                    if row:
                        candidates.append(row)
            for link in links:
                if (
                    link.startswith(("http://", "https://"))
                    and same_catalog(link, seed)
                    and link not in seen_pages
                    and len(seen_pages) < max_pages
                ):
                    seen_pages.add(link)
                    pages.append(link)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-pages", type=int, default=120)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))}

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
    rows: list[dict] = []
    inserted = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(crawl_seed, seed, args.max_pages): seed for seed in SEEDS}
        for future in as_completed(futures):
            seed = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"source_error {seed} {type(exc).__name__}", flush=True)
                continue
            print(f"source_done {seed} candidates={len(result)}", flush=True)
            rows.extend(result)
            unique = []
            for row in result:
                if row["canonical_key"] in existing:
                    continue
                existing.add(row["canonical_key"])
                unique.append(row)
            with engine.begin() as conn:
                for idx in range(0, len(unique), 500):
                    added = conn.execute(sql, unique[idx : idx + 500])
                    inserted += int(added.rowcount or 0)
            print(f"source_committed {seed} inserted={inserted}", flush=True)
    with engine.connect() as conn:
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
