from __future__ import annotations

from dataclasses import dataclass

from community_scanner.models import DiscoveryHit

DEFAULT_SCAN_GEO = "USA"


@dataclass(frozen=True)
class QueryParams:
    geo: str | None = DEFAULT_SCAN_GEO
    niche: str | None = None
    audience: str | None = None
    community_type: str | None = None


# USA-focused discovery templates ({geo} defaults to USA).
USA_TEMPLATES = [
    "{niche} {geo} community",
    "{niche} {geo} professional network",
    "best {niche} communities {geo}",
    "{audience} {niche} forum {geo}",
    "{niche} association {geo}",
    "paid {niche} community {geo}",
    "professional {niche} community {geo}",
    "{niche} founders community {geo}",
    "{niche} membership club {geo}",
    "site:skool.com {niche} {geo}",
    "site:circle.so {niche} {geo}",
    "site:mightynetworks.com {niche} {geo}",
    "{niche} community for {audience} {geo}",
    "private {niche} community paid {geo}",
    "{niche} peer group membership {geo}",
    "{niche} mastermind community {geo}",
    "{niche} slack community {geo}",
    "{niche} discord server {geo}",
    "executive {niche} community {geo}",
    "{niche} united states membership community",
]


def resolve_geo(geo: str | None) -> str:
    value = (geo or DEFAULT_SCAN_GEO).strip()
    return value or DEFAULT_SCAN_GEO


def generate_queries(params: QueryParams, limit: int = 50) -> list[str]:
    niche = params.niche or "business"
    geo = resolve_geo(params.geo)
    audience = params.audience or "professionals"
    community_type = params.community_type or "community"

    values = {
        "niche": niche,
        "geo": geo,
        "audience": audience,
        "type": community_type,
    }

    queries: list[str] = []
    for template in USA_TEMPLATES:
        q = " ".join(template.format(**values).split())
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= limit:
            break
    return queries


class DiscoveryProvider:
    name: str

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        raise NotImplementedError
