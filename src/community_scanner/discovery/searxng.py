from __future__ import annotations

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit


class SearxngProvider(DiscoveryProvider):
    name = "searxng"

    def __init__(self, base_url: str, timeout: float = 20.0, language: str = "en-US") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.language = language

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        hits: list[DiscoveryHit] = []
        page = 1
        max_pages = max(1, (count + 9) // 10)

        with httpx.Client(timeout=self.timeout) as client:
            while len(hits) < count and page <= max_pages:
                params = {
                    "q": query,
                    "format": "json",
                    "pageno": page,
                    "language": self.language,
                }
                resp = client.get(f"{self.base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results") or []
                if not results:
                    break

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

        return hits[:count]
