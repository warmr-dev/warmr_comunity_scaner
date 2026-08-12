from __future__ import annotations

from dataclasses import dataclass

from community_scanner.models import DiscoveryHit

DEFAULT_SCAN_GEO = "USA"

# IT and education niches for community chat harvesting.
IT_NICHES = (
    "software-engineering",
    "programming",
    "developers",
    "devops",
    "cybersecurity",
    "data-science",
    "artificial-intelligence",
    "machine-learning",
    "cloud-computing",
    "data-engineering",
    "web-development",
    "mobile-development",
    "open-source",
    "computer-science",
    "coding",
    "tech",
    "education",
    "edtech",
    "online-learning",
    "bootcamp",
)


@dataclass(frozen=True)
class QueryParams:
    geo: str | None = DEFAULT_SCAN_GEO
    niche: str | None = None
    audience: str | None = None
    community_type: str | None = None


# Queries focused on human chat groups/communities (not bots).
# Telegram: groups and supergroups only (t.me/+ = invite links to groups, not channels/bots).
# WhatsApp: group chats via chat.whatsapp.com.
# Slack: workspaces via join.slack.com or shared_invite.
# Discord: servers via disboard.org, discord.me, discord.gg (exclude bot-listing top.gg).
CHAT_TEMPLATES = [
    # --- Telegram groups (invite links = groups/supergroups, not bots) ---
    'inurl:t.me/+ "{niche}"',
    '"{niche}" site:t.me/+',
    '"{niche}" telegram group -bot',
    '"{niche}" telegram supergroup -bot',
    '"{niche}" telegram community group',
    "{niche} telegram group invite link",
    "{niche} telegram study group",
    "{niche} telegram learning group",
    "join {niche} telegram group",
    "best {niche} telegram groups",
    "{audience} {niche} telegram group",
    # --- Telegram directories (group-focused) ---
    'site:tgstat.com "{niche}" -bot',
    'site:telemetr.io "{niche}" -bot',
    # --- WhatsApp group chats ---
    'inurl:chat.whatsapp.com "{niche}"',
    '"{niche}" chat.whatsapp.com',
    '"{niche}" whatsapp group invite',
    "{niche} whatsapp group link",
    "join {niche} whatsapp group",
    "{niche} whatsapp study group",
    "{audience} {niche} whatsapp group",
    # --- Slack workspaces ---
    'inurl:join.slack.com "{niche}"',
    'inurl:slack.com/shared_invite "{niche}"',
    '"{niche}" join.slack.com',
    "{niche} slack workspace invite",
    "{niche} slack community workspace",
    "{audience} {niche} slack",
    # --- Discord servers (not bot lists) ---
    'site:disboard.org "{niche}"',
    'site:discord.me "{niche}"',
    'inurl:discord.gg "{niche}"',
    'inurl:discord.com/invite "{niche}"',
    '"{niche}" discord server invite -bot',
    "{niche} discord server community",
    "{niche} discord learning server",
    "{audience} {niche} discord server",
    # --- Cross-platform community lists ---
    '"{niche}" community telegram OR slack OR discord -bot',
    "{niche} online community chat group",
    "{niche} developer community chat",
    "{niche} study group telegram OR discord OR slack",
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
    for template in CHAT_TEMPLATES:
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
