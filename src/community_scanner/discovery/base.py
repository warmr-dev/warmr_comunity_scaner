from __future__ import annotations

from dataclasses import dataclass

from community_scanner.models import DiscoveryHit


@dataclass(frozen=True)
class QueryParams:
    geo: str | None = None
    niche: str | None = None
    audience: str | None = None
    community_type: str | None = None


TEMPLATES = [
    "{niche} {geo} community",
    "{niche} {geo} professional network",
    "{niche} {geo} membership club",
    "best {niche} communities {geo}",
    "{audience} {niche} forum {geo}",
    "{niche} association {geo}",
    "skool {niche} {geo}",
    "circle community {niche} {geo}",
]


def generate_queries(params: QueryParams, limit: int = 50) -> list[str]:
    niche = params.niche or "business"
    geo = params.geo or ""
    audience = params.audience or "professionals"
    community_type = params.community_type or "community"

    values = {
        "niche": niche,
        "geo": geo,
        "audience": audience,
        "type": community_type,
    }

    queries: list[str] = []
    for template in TEMPLATES:
        q = " ".join(template.format(**values).split())
        if q not in queries:
            queries.append(q)
        if len(queries) >= limit:
            break
    return queries


class DiscoveryProvider:
    name: str

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        raise NotImplementedError
