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


# Telegram + WhatsApp only — maximize invite/channel SERP surface.
USA_TEMPLATES = [
    # Telegram directories / operators
    "site:t.me {niche}",
    "site:telegram.me {niche}",
    "inurl:t.me {niche}",
    "inurl:t.me/+ {niche}",
    "inurl:joinchat {niche}",
    '"{niche}" "t.me/"',
    '"{niche}" "t.me/+"',
    '"{niche}" telegram channel',
    '"{niche}" telegram group',
    '"{niche}" telegram community',
    "{niche} telegram channel {geo}",
    "{niche} telegram group invite {geo}",
    "{niche} telegram chat {geo}",
    "{audience} {niche} telegram",
    "best {niche} telegram channels",
    "{niche} telegram list OR directory",
    # WhatsApp
    "site:chat.whatsapp.com {niche}",
    "inurl:chat.whatsapp.com {niche}",
    "inurl:whatsapp.com/channel {niche}",
    '"{niche}" chat.whatsapp.com/',
    '"{niche}" whatsapp group invite',
    '"{niche}" whatsapp community',
    "{niche} whatsapp group {geo}",
    "{niche} whatsapp invite link {geo}",
    "{niche} whatsapp channel {geo}",
    "{audience} {niche} whatsapp group",
    "join {niche} whatsapp group",
    "{niche} whatsapp community invite",
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
