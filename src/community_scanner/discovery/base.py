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

# Human-readable variants that Bing matches better than hyphenated slugs.
NICHE_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "software-engineering": ("software engineering", "software engineer", "programming"),
    "data-science": ("data science", "data scientist", "python"),
    "machine-learning": ("machine learning", "ml engineer", "deep learning"),
    "artificial-intelligence": ("artificial intelligence", "ai engineer", "ai"),
    "cloud-computing": ("cloud computing", "aws", "devops"),
    "web-development": ("web development", "web developer", "javascript"),
    "mobile-development": ("mobile development", "android developer", "ios developer"),
    "computer-science": ("computer science", "cs student", "programming"),
    "cybersecurity": ("cyber security", "infosec", "cybersecurity"),
    "data-engineering": ("data engineering", "data engineer"),
    "online-learning": ("online learning", "study group", "bootcamp"),
    "edtech": ("edtech", "education technology", "learning"),
}


@dataclass(frozen=True)
class QueryParams:
    geo: str | None = DEFAULT_SCAN_GEO
    niche: str | None = None
    audience: str | None = None
    community_type: str | None = None


# Invite-first templates. Hard inurl/site operators first — Bing often returns
# listicles for soft "telegram group" queries.
CHAT_TEMPLATES = [
    # --- Direct invite URLs (highest yield) ---
    'inurl:t.me/+ "{niche}"',
    'inurl:t.me/joinchat "{niche}"',
    'inurl:chat.whatsapp.com "{niche}"',
    'inurl:discord.gg "{niche}"',
    'inurl:discord.com/invite "{niche}"',
    'inurl:join.slack.com "{niche}"',
    'inurl:slack.com/shared_invite "{niche}"',
    'site:t.me "+{niche}"',
    '"{niche}" "t.me/+"',
    '"{niche}" "chat.whatsapp.com/"',
    '"{niche}" "discord.gg/"',
    '"{niche}" "join.slack.com/t/"',
    # --- Directories that expose real invites ---
    'site:tgstat.com/en "{niche}"',
    'site:tgstat.com "{niche}" telegram',
    'site:disboard.org/server "{niche}"',
    'site:discord.me "{niche}"',
    'site:discordservers.com "{niche}"',
    # --- Soft fallbacks (lower priority) ---
    '"{niche}" telegram invite link -bot -channel',
    '"{niche}" whatsapp group invite link',
    '"{niche}" discord invite link -bot',
    '"{niche}" slack invite link workspace',
    "join {niche} telegram group invite",
    "join {niche} discord server invite",
    "{audience} {niche} telegram group invite",
    "{audience} {niche} discord invite",
]


def resolve_geo(geo: str | None) -> str:
    value = (geo or DEFAULT_SCAN_GEO).strip()
    return value or DEFAULT_SCAN_GEO


def niche_query_terms(niche: str) -> list[str]:
    raw = (niche or "software-engineering").strip()
    spaced = raw.replace("-", " ").replace("_", " ").strip()
    terms: list[str] = []
    for term in (raw, spaced, *NICHE_QUERY_ALIASES.get(raw.lower(), ())):
        t = " ".join(term.split())
        if t and t.lower() not in {x.lower() for x in terms}:
            terms.append(t)
    return terms or [raw]


def generate_queries(params: QueryParams, limit: int = 50) -> list[str]:
    niche = params.niche or "software-engineering"
    geo = resolve_geo(params.geo)
    audience = params.audience or "developers"
    community_type = params.community_type or "community"
    niche_terms = niche_query_terms(niche)

    queries: list[str] = []
    seen: set[str] = set()
    for term in niche_terms:
        values = {
            "niche": term,
            "geo": geo,
            "audience": audience,
            "type": community_type,
        }
        for template in CHAT_TEMPLATES:
            q = " ".join(template.format(**values).split())
            key = q.lower()
            if not q or key in seen:
                continue
            seen.add(key)
            queries.append(q)
            if len(queries) >= limit:
                return queries
    return queries


class DiscoveryProvider:
    name: str

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        raise NotImplementedError
