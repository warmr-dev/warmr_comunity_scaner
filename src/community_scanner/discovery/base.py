from __future__ import annotations

from dataclasses import dataclass

from community_scanner.models import DiscoveryHit

DEFAULT_SCAN_GEO = "USA"

# IT-focused niches for volume invite harvesting.
IT_NICHES = (
    "it",
    "software-engineering",
    "programming",
    "developers",
    "devops",
    "cybersecurity",
    "data-science",
    "ai",
    "machine-learning",
    "cloud-computing",
    "data-engineering",
    "devtools",
    "saas",
    "startups",
    "web-development",
    "mobile-development",
    "blockchain",
    "open-source",
    "education",
    "edtech",
    "computer-science",
    "coding",
    "tech",
)


@dataclass(frozen=True)
class QueryParams:
    geo: str | None = DEFAULT_SCAN_GEO
    niche: str | None = None
    audience: str | None = None
    community_type: str | None = None


# Maximum surface area: directories + inurl + quoted invite patterns for all chat platforms.
USA_TEMPLATES = [
    # --- Telegram ---
    "site:tgstat.com {niche}",
    "site:tgstat.ru {niche}",
    "site:telemetr.io {niche}",
    "site:combot.org {niche}",
    "site:tlgrm.ru {niche}",
    "site:t.me {niche}",
    "inurl:t.me {niche}",
    "inurl:t.me/+ {niche}",
    '"{niche}" "t.me/"',
    '"{niche}" "t.me/+"',
    "{niche} telegram channel",
    "{niche} telegram group invite",
    "{niche} telegram community {geo}",
    "best {niche} telegram channels",
    "{audience} {niche} telegram",
    # --- WhatsApp ---
    "site:chat.whatsapp.com {niche}",
    "inurl:chat.whatsapp.com {niche}",
    "inurl:whatsapp.com/channel {niche}",
    '"{niche}" chat.whatsapp.com',
    '"{niche}" whatsapp group invite',
    "{niche} whatsapp group link",
    "{niche} whatsapp community {geo}",
    "join {niche} whatsapp group",
    "{audience} {niche} whatsapp",
    # --- Slack ---
    "site:join.slack.com {niche}",
    "inurl:join.slack.com {niche}",
    "inurl:shared_invite {niche}",
    '"{niche}" join.slack.com',
    '"{niche}" slack.com/shared_invite',
    "{niche} slack invite",
    "{niche} slack workspace",
    "{niche} slack community",
    "{audience} {niche} slack",
    # --- Discord ---
    "site:disboard.org {niche}",
    "site:disboard.org/server {niche}",
    "site:top.gg {niche}",
    "site:discord.me {niche}",
    "site:discord.gg {niche}",
    "inurl:discord.gg {niche}",
    "inurl:discord.com/invite {niche}",
    '"{niche}" discord.gg',
    '"{niche}" discord invite',
    "{niche} discord server invite",
    "{niche} discord community {geo}",
    "{audience} {niche} discord",
    # --- Cross-platform IT lists ---
    "{niche} community slack OR telegram OR discord",
    "{niche} developer chat invite",
    "{niche} tech community invite link",
    "IT {niche} group chat invite",
]


def resolve_geo(geo: str | None) -> str:
    value = (geo or DEFAULT_SCAN_GEO).strip()
    return value or DEFAULT_SCAN_GEO


def generate_queries(params: QueryParams, limit: int = 50) -> list[str]:
    niche = params.niche or "software-engineering"
    geo = resolve_geo(params.geo)
    audience = params.audience or "developers"
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
