"""Hive Index directory crawler as DiscoveryProvider."""

from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import httpx

from community_scanner.discovery.base import DiscoveryProvider, QueryParams
from community_scanner.invites import find_all_invites_in_text
from community_scanner.models import DiscoveryHit

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

PLATFORM_PAGES = (
    "https://thehiveindex.com/platforms/slack/",
    "https://thehiveindex.com/platforms/skool/",
    "https://thehiveindex.com/platforms/circle/",
    "https://thehiveindex.com/platforms/whatsapp/",
    "https://thehiveindex.com/platforms/facebook/",
    "https://thehiveindex.com/platforms/linkedin/",
    "https://thehiveindex.com/platforms/reddit/",
)

TOPIC_PAGES = (
    "https://thehiveindex.com/topics/entrepreneurship/",
    "https://thehiveindex.com/topics/software-development/",
    "https://thehiveindex.com/topics/marketing/",
    "https://thehiveindex.com/topics/investing/",
    "https://thehiveindex.com/topics/product-management/",
    "https://thehiveindex.com/topics/sales/",
    "https://thehiveindex.com/topics/artificial-intelligence/",
    "https://thehiveindex.com/topics/design/",
    "https://thehiveindex.com/topics/fitness/",
)

# Excluded in mass mode (no Discord/Telegram primary).
EXCLUDED_INVITE_PLATFORMS = frozenset({"discord", "telegram"})


def _community_pages(html: str, base: str) -> set[str]:
    out: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', html):
        abs_url = urljoin(base, href).split("#")[0]
        path = urlparse(abs_url).path.rstrip("/")
        if path.startswith("/communities/") and path.count("/") >= 2:
            out.add(abs_url if abs_url.endswith("/") else abs_url + "/")
    return out


class HiveIndexProvider(DiscoveryProvider):
    name = "hive"

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        delay: float = 0.35,
        max_detail_pages: int = 400,
        exclude_discord_telegram: bool = True,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.max_detail_pages = max_detail_pages
        self.exclude_discord_telegram = exclude_discord_telegram

    def crawl(self, params: QueryParams, count: int = 100) -> list[DiscoveryHit]:
        niche = (params.niche or "").strip().lower()
        hits: list[DiscoveryHit] = []
        seen: set[str] = set()
        listing_urls = list(PLATFORM_PAGES) + list(TOPIC_PAGES)
        community_urls: list[str] = []
        seen_pages: set[str] = set()

        with httpx.Client(
            timeout=self.timeout,
            headers=HEADERS,
            follow_redirects=True,
        ) as client:
            for listing in listing_urls:
                if self.delay:
                    time.sleep(self.delay)
                try:
                    resp = client.get(listing)
                    if resp.status_code >= 400:
                        continue
                    for page in _community_pages(resp.text or "", listing):
                        key = page.lower()
                        if key in seen_pages:
                            continue
                        if niche and niche not in {"harvest", "all", "any", "business"}:
                            token = niche.replace("-", " ").split()[0]
                            if token and token not in page.lower() and len(token) > 3:
                                # Keep platform listings even when niche filter is set;
                                # topic pages already narrow somewhat.
                                if "/topics/" in listing:
                                    continue
                        seen_pages.add(key)
                        community_urls.append(page)
                except Exception:  # noqa: BLE001
                    continue

            detail_budget = min(len(community_urls), self.max_detail_pages, max(count, 1))
            print(
                f"hive listing communities={len(community_urls)} "
                f"detail_budget={detail_budget}",
                flush=True,
            )

            for page_url in community_urls[:detail_budget]:
                if len(hits) >= count:
                    break
                if self.delay:
                    time.sleep(self.delay)
                try:
                    resp = client.get(page_url)
                    if resp.status_code >= 400:
                        continue
                    html = (resp.text or "").replace("&amp;", "&")
                except Exception:  # noqa: BLE001
                    continue

                title_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
                title = title_match.group(1).strip() if title_match else None
                invites = find_all_invites_in_text(html, limit=20)
                added = False
                for invite in invites:
                    if self.exclude_discord_telegram and invite.platform in EXCLUDED_INVITE_PLATFORMS:
                        continue
                    key = invite.url.lower().rstrip("/")
                    if key in seen:
                        continue
                    seen.add(key)
                    hits.append(
                        DiscoveryHit(
                            url=invite.url,
                            title=title,
                            snippet=f"hive={page_url}",
                            provider=self.name,
                            query=params.niche,
                        )
                    )
                    added = True
                    if len(hits) >= count:
                        break
                if not added:
                    # Keep hive community page itself as a watch candidate.
                    key = page_url.lower().rstrip("/")
                    if key not in seen:
                        seen.add(key)
                        hits.append(
                            DiscoveryHit(
                                url=page_url,
                                title=title,
                                snippet="hive_listing_only",
                                provider=self.name,
                                query=params.niche,
                            )
                        )

        print(f"hive done hits={len(hits)}", flush=True)
        return hits

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        return self.crawl(QueryParams(niche=query or "harvest"), count=count)
