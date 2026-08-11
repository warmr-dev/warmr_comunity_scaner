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


# Directories + invite operators for Telegram / WhatsApp / Slack.
# Goal: land on list pages that contain many invite URLs, then extract all of them.
USA_TEMPLATES = [
    # Telegram directories
    "site:tgstat.com {niche}",
    "site:tgstat.ru {niche}",
    "site:telemetr.io {niche}",
    "site:combot.org {niche}",
    "site:tlgrm.ru {niche}",
    "site:t.me {niche}",
    "inurl:t.me {niche}",
    "inurl:t.me/+ {niche}",
    '"{niche}" "t.me/" telegram',
    '"{niche}" "t.me/+"',
    "{niche} telegram channel list",
    "{niche} telegram group invite",
    "{niche} telegram channels {geo}",
    "best {niche} telegram channels",
    "{audience} {niche} telegram group",
    # WhatsApp directories / lists
    "site:chat.whatsapp.com {niche}",
    "inurl:chat.whatsapp.com {niche}",
    "inurl:whatsapp.com/channel {niche}",
    '"{niche}" chat.whatsapp.com',
    '"{niche}" "whatsapp group invite"',
    "{niche} whatsapp group link",
    "{niche} whatsapp group invite {geo}",
    "{niche} whatsapp community invite",
    "join {niche} whatsapp group",
    "{audience} {niche} whatsapp group",
    "best {niche} whatsapp groups",
    # Slack
    "site:join.slack.com {niche}",
    "inurl:join.slack.com {niche}",
    "inurl:shared_invite {niche}",
    '"{niche}" join.slack.com',
    '"{niche}" slack.com/shared_invite',
    "{niche} slack invite {geo}",
    "{niche} slack community invite",
    "{niche} slack workspace {geo}",
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
