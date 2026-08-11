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


# Prefer directories + inurl operators — Bing rarely indexes bare invite URLs in generic SERP.
USA_TEMPLATES = [
    "site:disboard.org {niche}",
    "site:disboard.org/server {niche}",
    "site:top.gg/servers {niche}",
    "site:discord.me {niche}",
    "inurl:discord.gg {niche}",
    "inurl:discord.com/invite {niche}",
    "inurl:chat.whatsapp.com {niche}",
    "inurl:join.slack.com {niche}",
    "inurl:shared_invite {niche}",
    "site:t.me {niche}",
    "inurl:t.me {niche}",
    '"{niche}" discord.gg/',
    '"{niche}" chat.whatsapp.com/',
    '"{niche}" join.slack.com/t/',
    '"{niche}" "t.me/+"',
    "{niche} discord server invite {geo}",
    "{niche} slack workspace invite {geo}",
    "{niche} telegram group {geo} t.me",
    "{niche} whatsapp group invite {geo}",
    "site:discord.gg {niche}",
    "site:chat.whatsapp.com {niche}",
    "site:join.slack.com {niche}",
    "{audience} {niche} discord invite",
    "{audience} {niche} slack invite",
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
