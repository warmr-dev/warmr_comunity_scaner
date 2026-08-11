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


# Invite-first discovery: surface Slack / WhatsApp / Telegram / Discord join links.
# Generic "community" SERPs almost never contain direct chat invites.
USA_TEMPLATES = [
    '"{niche}" "join.slack.com"',
    '"{niche}" slack.com/shared_invite',
    '"{niche}" slack invite {geo}',
    '"{niche}" slack community invite',
    "{niche} professionals slack workspace",
    '"{niche}" chat.whatsapp.com',
    '"{niche}" whatsapp group invite {geo}',
    '"{niche}" whatsapp community invite',
    '"{niche}" "t.me/+" OR "t.me/joinchat"',
    '"{niche}" telegram group invite {geo}',
    '"{niche}" telegram channel {geo}',
    '"{niche}" discord.gg',
    '"{niche}" discord.com/invite',
    "{niche} discord invite {geo}",
    "site:join.slack.com {niche}",
    "site:chat.whatsapp.com {niche}",
    "site:t.me {niche}",
    "site:discord.gg {niche}",
    "{niche} founders slack invite",
    "{niche} founders discord invite",
    "{niche} mastermind slack invite",
    "{niche} peer group whatsapp",
    "{audience} {niche} slack invite",
    "{audience} {niche} telegram group",
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
