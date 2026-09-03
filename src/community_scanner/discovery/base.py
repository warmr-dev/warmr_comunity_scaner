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


# High-signal first: paid/pro communities that can reach medium/high value_tier.
HARVEST_TEMPLATES = [
    # Paid / membership (Warmr high-value)
    "paid community membership invite OR join founders OR operators",
    "mastermind community invite slack OR skool OR circle",
    '"$/mo" OR "$/month" skool community OR circle.so community',
    "founder community slack invite link",
    "CEO peer community invite OR membership",
    "professional community membership site:skool.com OR site:circle.so",
    # Slack invites (priority)
    "inurl:join.slack.com/t/",
    "inurl:slack.com/shared_invite",
    '"join.slack.com/t/" invite OR workspace OR community',
    '"shared_invite" site:slack.com',
    "slack workspace invite link professionals OR founders",
    'site:notion.so "join.slack.com"',
    'site:github.com "join.slack.com/t/"',
    # Skool / Circle
    "site:skool.com",
    '"skool.com/" community OR membership OR join',
    "skool community paid OR membership",
    "site:circle.so",
    '"circle.so" community OR membership',
    # Facebook / LinkedIn groups
    "site:facebook.com/groups professional OR founders OR CPA OR lawyers",
    'inurl:facebook.com/groups/ "join" OR community',
    "site:linkedin.com/groups professional OR founders OR marketing",
    'inurl:linkedin.com/groups/',
    # Hive Index directory
    "site:thehiveindex.com community slack OR circle OR facebook OR telegram",
    "site:thehiveindex.com/communities/",
    # WhatsApp pro groups
    "inurl:chat.whatsapp.com",
    '"chat.whatsapp.com/" professionals OR founders OR CPA OR lawyers',
    # Telegram groups (not channels)
    "inurl:t.me/+ professional OR founders OR developers group chat",
    '"t.me/+" invite group professionals -channel -subscribers',
    'telegram group chat "members" founders OR developers OR marketing -channel',
]

# Soft niche variants appended in harvest when a niche is set.
HARVEST_NICHE_TEMPLATES = [
    'inurl:join.slack.com "{niche}"',
    '"{niche}" "join.slack.com/t/" invite OR workspace',
    '"{niche}" paid community OR membership skool OR circle OR slack',
    '"{niche}" mastermind invite OR community',
    'site:skool.com "{niche}"',
    'site:circle.so "{niche}"',
    'site:facebook.com/groups "{niche}"',
    'site:linkedin.com/groups "{niche}"',
    'site:thehiveindex.com "{niche}"',
    'inurl:chat.whatsapp.com "{niche}"',
    '"{niche}" telegram group chat "t.me/" -channel',
]

# Niche-first templates (used when HARVEST_MODE=false).
CHAT_TEMPLATES = [
    '"{niche}" paid community membership',
    '"{niche}" mastermind community invite',
    'inurl:join.slack.com "{niche}"',
    '"{niche}" "join.slack.com/t/"',
    '"{niche}" slack invite link founders OR professionals',
    'site:skool.com "{niche}"',
    '"{niche}" site:skool.com membership',
    'site:circle.so "{niche}"',
    '"{niche}" circle.so community',
    'site:facebook.com/groups "{niche}"',
    'site:linkedin.com/groups "{niche}"',
    'inurl:chat.whatsapp.com "{niche}"',
    '"{niche}" telegram group "t.me/" -channel',
    "{audience} {niche} slack community invite",
    "{audience} {niche} skool community",
    "{audience} {niche} facebook group",
    "{audience} {niche} linkedin group",
    "{audience} {niche} paid community",
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


def generate_queries(
    params: QueryParams,
    limit: int = 50,
    *,
    harvest: bool = False,
) -> list[str]:
    niche = params.niche or "software-engineering"
    geo = resolve_geo(params.geo)
    audience = params.audience or "developers"
    community_type = params.community_type or "community"
    niche_lc = niche.strip().lower()
    niche_is_broad = niche_lc in {"", "harvest", "all", "any", "invites"}

    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> bool:
        q = " ".join(q.split())
        key = q.lower()
        if not q or key in seen:
            return len(queries) >= limit
        seen.add(key)
        queries.append(q)
        return len(queries) >= limit

    if harvest:
        # Niche-first: when a concrete niche is set, search it before generic templates.
        if not niche_is_broad:
            for term in niche_query_terms(niche)[:3]:
                values = {"niche": term, "geo": geo, "audience": audience, "type": community_type}
                for template in HARVEST_NICHE_TEMPLATES:
                    if _add(template.format(**values)):
                        return queries
        for template in HARVEST_TEMPLATES:
            if _add(template):
                return queries
        return queries

    niche_terms = niche_query_terms(niche)
    for term in niche_terms:
        values = {
            "niche": term,
            "geo": geo,
            "audience": audience,
            "type": community_type,
        }
        for template in CHAT_TEMPLATES:
            if _add(template.format(**values)):
                return queries
    return queries


class DiscoveryProvider:
    name: str

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        raise NotImplementedError
