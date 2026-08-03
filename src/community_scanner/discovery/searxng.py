from __future__ import annotations

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit


class SearxngProvider(DiscoveryProvider):
    name = "searxng"

    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        params = {"q": query, "format": "json"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(f"{self.base_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        hits: list[DiscoveryHit] = []
        for item in data.get("results", [])[:count]:
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
        return hits
