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


# High-signal USA community discovery templates.
# Avoid bare "paid" / "professional" — they pollute SERP with dictionaries.
USA_TEMPLATES = [
    "site:skool.com {niche}",
    "site:circle.so {niche}",
    "site:mightynetworks.com {niche}",
    "site:discord.gg {niche}",
    "site:facebook.com/groups {niche}",
    "site:linkedin.com/groups {niche}",
    '"{niche}" membership community {geo}',
    '"{niche}" online community {geo}',
    '"{niche}" forum community {geo}',
    "{niche} association members {geo}",
    "{niche} chapter network {geo}",
    "{niche} mastermind group {geo}",
    "{niche} peer advisory group {geo}",
    "{niche} founders community slack",
    "{niche} founders community discord",
    "{niche} professionals community skool",
    "{niche} membership club apply {geo}",
    "best {niche} online communities {geo} skool OR circle OR discord",
    "{niche} trade association {geo}",
    "{niche} industry association {geo}",
    "{audience} {niche} community membership",
    "{niche} community of practice {geo}",
    "{niche} private community {geo}",
    "{niche} paid community {geo}",
    "{niche} networking group {geo}",
    "{niche} slack community {geo}",
    "{niche} discord community {geo}",
    "{niche} facebook group {geo}",
    "{niche} meetup group {geo}",
    "top {niche} communities {geo}",
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
