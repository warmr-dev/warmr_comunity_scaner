from __future__ import annotations

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit


class BraveSearchProvider(DiscoveryProvider):
    name = "brave"

    def __init__(self, api_key: str, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        if not self.api_key:
            return []

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {"q": query, "count": min(count, 20)}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        hits: list[DiscoveryHit] = []
        for item in data.get("web", {}).get("results", [])[:count]:
            url = item.get("url")
            if not url:
                continue
            hits.append(
                DiscoveryHit(
                    url=url,
                    title=item.get("title"),
                    snippet=item.get("description"),
                    provider=self.name,
                    query=query,
                )
            )
        return hits
