from __future__ import annotations

import time

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit


class SearxngProvider(DiscoveryProvider):
    name = "searxng"

    def __init__(self, base_url: str, timeout: float = 20.0, language: str = "en-US") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language
        # Bing is the most reliable public engine from Railway/datacenter IPs.
        # Brave/Mojeek hit 429/timeout within minutes and poison the run.
        self.engines = "bing"
        self._cooldown_until = 0.0

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        hits: list[DiscoveryHit] = []
        page = 1
        max_pages = max(1, (count + 9) // 10)
        empty_streak = 0

        with httpx.Client(timeout=self.timeout) as client:
            while len(hits) < count and page <= max_pages:
                now = time.monotonic()
                if now < self._cooldown_until:
                    time.sleep(self._cooldown_until - now)

                params = {
                    "q": query,
                    "format": "json",
                    "pageno": page,
                    "language": self.language,
                    "engines": self.engines,
                }
                resp = client.get(f"{self.base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results") or []
                unresponsive = data.get("unresponsive_engines") or []
                if not results:
                    empty_streak += 1
                    if unresponsive:
                        print(
                            f"searxng empty for q={query!r} page={page}: {unresponsive}",
                            flush=True,
                        )
                        # Back off hard when engines are rate-limited.
                        self._cooldown_until = time.monotonic() + min(60.0, 8.0 * empty_streak)
                        time.sleep(min(20.0, 4.0 * empty_streak))
                    if empty_streak >= 2:
                        break
                    page += 1
                    continue

                empty_streak = 0
                for item in results:
                    url = item.get("url")
                    if not url:
                        continue
                    hits.append(
                        DiscoveryHit(
                            url=url,
                            title=item.get("title"),
                            snippet=item.get("content"),
                            provider=self.name,
                            query=query,
                        )
                    )
                    if len(hits) >= count:
                        break
                page += 1
                if page <= max_pages and len(hits) < count:
                    time.sleep(1.0)

        return hits[:count]
