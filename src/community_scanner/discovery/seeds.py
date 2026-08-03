from __future__ import annotations

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit

# High-signal seed URLs for smoke / bootstrap. Replace/extend from Warmr ops.
DEFAULT_SEEDS: list[tuple[str, str, str]] = [
    (
        "https://www.skool.com/discovery",
        "Skool discovery",
        "community skool accounting business",
    ),
    (
        "https://www.indiehackers.com/",
        "Indie Hackers",
        "entrepreneur community founders",
    ),
    (
        "https://www.producthunt.com/",
        "Product Hunt",
        "startup makers community",
    ),
]


class SeedsProvider(DiscoveryProvider):
    name = "seeds"

    def __init__(self, seeds: list[tuple[str, str, str]] | None = None) -> None:
        self.seeds = seeds or DEFAULT_SEEDS

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        q = query.lower()
        hits: list[DiscoveryHit] = []
        for url, title, tag in self.seeds:
            if any(token in tag or token in title.lower() for token in q.split() if len(token) > 3):
                hits.append(
                    DiscoveryHit(url=url, title=title, snippet=tag, provider=self.name, query=query)
                )
            if len(hits) >= count:
                break
        # If nothing matched, still return a few seeds so local smoke works
        if not hits:
            for url, title, tag in self.seeds[: min(count, 3)]:
                hits.append(
                    DiscoveryHit(url=url, title=title, snippet=tag, provider=self.name, query=query)
                )
        return hits
