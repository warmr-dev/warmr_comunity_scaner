from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, unquote

# Telegram + WhatsApp + Slack + Discord invite URL patterns.
_SLACK_SHARED = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)?slack\.com/(?:shared_invite/[A-Za-z0-9_-]+|ssb/redirect)",
    re.I,
)
_SLACK_JOIN = re.compile(
    r"(?:https?://)?join\.slack\.com/t/[A-Za-z0-9_-]+(?:/[^\s\"'<>]*)?",
    re.I,
)
_SLACK_WORKSPACE = re.compile(
    r"(?:https?://)?([a-z0-9][a-z0-9-]{1,62})\.slack\.com(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_WHATSAPP_CHAT = re.compile(
    r"(?:https?://)?(?:chat\.whatsapp\.com|whatsapp\.com/channel)/([A-Za-z0-9_-]+)",
    re.I,
)
_TELEGRAM = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.I,
)
_TELEGRAM_PUBLIC = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,})/?(?:\d+)?(?:\?|$|[\"'\s<>])",
    re.I,
)
_DISCORD = re.compile(
    r"(?:https?://)?(?:discord\.gg|discord\.com/invite)/([A-Za-z0-9_-]+)",
    re.I,
)
_SKOOL = re.compile(
    r"(?:https?://)?(?:www\d*\.)?skool\.com/([a-z0-9][a-z0-9_-]{1,40})(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_CIRCLE_SUB = re.compile(
    r"(?:https?://)?([a-z0-9][a-z0-9-]{1,62})\.circle\.so(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_CIRCLE_PATH = re.compile(
    r"(?:https?://)?(?:www\.)?circle\.so/(?:c/)?([A-Za-z0-9][A-Za-z0-9_-]{1,64})(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_FACEBOOK_GROUP = re.compile(
    r"(?:https?://)?(?:www\.)?facebook\.com/groups/([A-Za-z0-9._-]+)(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_LINKEDIN_GROUP = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/groups/([0-9]{3,12})(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_REDDIT_COMMUNITY = re.compile(
    r"(?:https?://)?(?:www\.)?(?:reddit\.com|old\.reddit\.com)/r/([A-Za-z0-9_]+)(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_GITHUB_DISCUSSION = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/discussions(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_STACKEXCHANGE_CHAT = re.compile(
    r"(?:https?://)?chat\.stackexchange\.com/rooms/([0-9]+)(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_MATRIX_ROOM = re.compile(
    r"(?:https?://)?(?:www\.)?matrixrooms\.info/room/([A-Za-z0-9_!:#.-]+)(?:/|$|\?|[\"'\s<>])",
    re.I,
)
_ZULIP_COMMUNITY = re.compile(
    r"(?:https?://)?([A-Za-z0-9-]+)\.zulipchat\.com(?:/|$|\?|[\"'\s<>])",
    re.I,
)

_BARE_SLACK = re.compile(r"^https?://(?:www\.)?slack\.com/?$", re.I)

# Slack product/marketing hosts — not joinable communities.
_SLACK_SYSTEM_HOSTS = frozenset(
    {
        "app",
        "api",
        "status",
        "slack",
        "www",
        "get",
        "help",
        "join",
        "dev",
        "developer",
        "developers",
        "files",
        "edge",
        "hooks",
        "corp",
        "enterprise",
        "admin",
        "signin",
        "login",
        "docs",
        "support",
        "blog",
        "store",
        "download",
        "downloads",
        "mobile",
        "desktop",
        "sales",
        "partners",
        "security",
        "legal",
        "privacy",
        "careers",
        "about",
        "cdn",
        "auth",
        "sso",
        "billing",
        "marketplace",
        "apps",
        "bot",
        "bots",
        "connect",
        "demo",
        "sandbox",
        "example",
        "sample",
        "test",
        "staging",
        "community",
        "communities",
        "workspace-signin",
        "solutions",
        "resources",
        "intl",
        "ssb",
        "go",
        "my",
        "a",
        "b",
        "mail",
        "email",
        "feedback",
        "brand",
        "newsroom",
        "trust",
        "slackb",
        "slackhq",
        "slack-marketing",
        "slack-sales-and-cs",
        "xyz",
        "null",
        "undefined",
    }
)

_SKOOL_BLOCKED = {
    "discovery",
    "about",
    "login",
    "signup",
    "sign-up",
    "pricing",
    "explore",
    "search",
    "settings",
    "admin",
    "api",
    "help",
    "blog",
    "article",
    "category",
    "collection",
    "live",
    "ws",
    "skool",
    "your-name",
    "cdn-cgi",
    "privacy-policy",
    "skool-games",
    "skool-pricing",
    "skool-review",
    "skool-free-trial",
    "14day-trial",
}
_CIRCLE_BLOCKED = {
    "www",
    "app",
    "login",
    "signup",
    "pricing",
    "blog",
    "help",
    "api",
    "status",
    "circle",
    "cdn",
    "cdn-marketing",
    "assets",
    "assets-v3",
    "asset-pipeline",
    "inbox",
    "products",
    "analytics",
    "users",
    "home",
    "welcome",
    "media",
    "images",
    "discover",
    "academy",
    "terms",
    "plus",
    "fr",
    "br",
    "integrations",
    "gamification",
    "customization",
    "headless",
    "studios",
    "discussions",
    "introduce-yourself",
}

# Platforms kept as useful Warmr community sources.
ACTIVE_HARVEST_PLATFORMS = frozenset(
    {
        "slack",
        "whatsapp",
        "skool",
        "circle",
        "telegram",
        "facebook",
        "linkedin",
        "reddit",
        "discourse",
        "matrix",
        "geneva",
        "mattermost",
        "zulip",
        "github",
        "stackexchange",
        "disqus",
    }
)

_TELEGRAM_BLOCKED = {
    "share",
    "joinchat",
    "addstickers",
    "proxy",
    "socks",
    "iv",
    "s",
    "c",
    "login",
    "setlanguage",
    "premium",
    "boost",
    "telegram",
    "desktop",
    "telegramtips",
    "discord",
    "whatsapp",
    "download",
    "developers",
}

# Require proven audience before upsert when count is known.
MIN_MEMBERS_FOR_UPSERT = 100
# Datacenter IPs often cannot scrape invite landing pages for public counts.
# Allow shaped invites without size; still reject known-too-small.
SIZE_OPTIONAL_PLATFORMS = frozenset(
    {"whatsapp", "slack", "skool", "circle", "telegram", "facebook", "linkedin"}
)
INVITE_SCAN_LIMIT = 500


@dataclass(frozen=True)
class InviteMatch:
    url: str
    platform: str
    rule: str


def _ensure_https(url: str) -> str:
    url = (url or "").strip().rstrip(".,);]")
    if url.startswith("//"):
        return "https:" + url
    if not url.lower().startswith(("http://", "https://")):
        return "https://" + url.lstrip("/")
    return url


def _normalize_candidate(url: str) -> str | None:
    url = _ensure_https(url)
    if not url.lower().startswith(("http://", "https://")):
        return None
    return url.split("#", 1)[0].rstrip()


def classify_invite_url(url: str) -> InviteMatch | None:
    """Return InviteMatch for Telegram / WhatsApp / Slack / Discord join links."""
    from urllib.parse import unquote

    url = _normalize_candidate(unquote((url or "").replace("%2B", "+").replace("%2b", "+")))
    if not url:
        return None
    if _BARE_SLACK.match(url):
        return None

    m = _SLACK_JOIN.search(url) or _SLACK_SHARED.search(url)
    if m:
        return InviteMatch(url=_ensure_https(m.group(0)), platform="slack", rule="slack_shared_invite")

    # Bare workspace homes (foo.slack.com) are usually login walls, not join links.
    # Keep only real invite URLs for harvest quality.
    m = _SLACK_WORKSPACE.match(url) or _SLACK_WORKSPACE.search(url + " ")
    if m:
        return None

    m = _WHATSAPP_CHAT.search(url)
    if m:
        code = m.group(1)
        # Channels are usually one-way broadcast spam for Warmr; keep group chats only.
        if "channel" in m.group(0).lower():
            return None
        return InviteMatch(
            url=f"https://chat.whatsapp.com/{code}",
            platform="whatsapp",
            rule="whatsapp_chat_invite",
        )

    m = _SKOOL.search(url)
    if m:
        slug = m.group(1).lower()
        if slug not in _SKOOL_BLOCKED:
            return InviteMatch(
                url=f"https://www.skool.com/{m.group(1)}",
                platform="skool",
                rule="skool_community",
            )

    m = _CIRCLE_SUB.search(url)
    if m:
        slug = m.group(1).lower()
        if slug not in _CIRCLE_BLOCKED:
            return InviteMatch(
                url=f"https://{m.group(1)}.circle.so",
                platform="circle",
                rule="circle_subdomain",
            )

    # circle.so/c/<slug> is marketing/app chrome — not accepted.

    m = _FACEBOOK_GROUP.search(url)
    if m:
        slug = m.group(1)
        if slug.lower() not in {"directory", "create", "feed", "discover"}:
            return InviteMatch(
                url=f"https://www.facebook.com/groups/{slug}",
                platform="facebook",
                rule="facebook_group",
            )

    m = _LINKEDIN_GROUP.search(url)
    if m:
        return InviteMatch(
            url=f"https://www.linkedin.com/groups/{m.group(1)}",
            platform="linkedin",
            rule="linkedin_group",
        )

    m = _REDDIT_COMMUNITY.search(url)
    if m:
        return InviteMatch(
            url=f"https://www.reddit.com/r/{m.group(1)}",
            platform="reddit",
            rule="reddit_community",
        )

    m = _GITHUB_DISCUSSION.search(url)
    if m:
        return InviteMatch(
            url=f"https://github.com/{m.group(1)}/discussions",
            platform="github",
            rule="github_discussions",
        )

    m = _STACKEXCHANGE_CHAT.search(url)
    if m:
        return InviteMatch(
            url=f"https://chat.stackexchange.com/rooms/{m.group(1)}",
            platform="stackexchange",
            rule="stackexchange_chat",
        )

    m = _MATRIX_ROOM.search(url)
    if m:
        return InviteMatch(
            url=_ensure_https(m.group(0)),
            platform="matrix",
            rule="matrix_room",
        )

    m = _ZULIP_COMMUNITY.search(url)
    if m:
        return InviteMatch(
            url=f"https://{m.group(1)}.zulipchat.com",
            platform="zulip",
            rule="zulip_community",
        )

    # Telegram / Discord still classified for legacy tooling/tests; upsert skips them.
    m = _TELEGRAM.search(url)
    if m:
        return InviteMatch(url=_ensure_https(m.group(0)), platform="telegram", rule="telegram_invite")

    m = _TELEGRAM_PUBLIC.match(url) or _TELEGRAM_PUBLIC.search(url + " ")
    if m:
        username = m.group(1).lower()
        if username in _TELEGRAM_BLOCKED:
            return None
        return InviteMatch(
            url=f"https://t.me/{m.group(1)}",
            platform="telegram",
            rule="telegram_public",
        )

    m = _DISCORD.search(url)
    if m:
        return InviteMatch(
            url=f"https://discord.gg/{m.group(1)}",
            platform="discord",
            rule="discord_invite",
        )

    return None


def find_invite_in_text(text: str) -> InviteMatch | None:
    matches = find_all_invites_in_text(text)
    return matches[0] if matches else None


def find_all_invites_in_text(text: str, *, limit: int = INVITE_SCAN_LIMIT) -> list[InviteMatch]:
    """Collect unique chat invites from free text / HTML."""
    if not text:
        return []
    text = (
        unquote(text.replace("&amp;", "&").replace("&#x2F;", "/").replace("&#47;", "/"))
        .replace("%2B", "+")
        .replace("%2b", "+")
    )
    patterns = (
        _SLACK_JOIN,
        _SLACK_SHARED,
        _WHATSAPP_CHAT,
        _SKOOL,
        _CIRCLE_SUB,
        _FACEBOOK_GROUP,
        _LINKEDIN_GROUP,
        _REDDIT_COMMUNITY,
        _GITHUB_DISCUSSION,
        _STACKEXCHANGE_CHAT,
        _MATRIX_ROOM,
        _ZULIP_COMMUNITY,
        _SLACK_WORKSPACE,
        _TELEGRAM,
        _DISCORD,
        _TELEGRAM_PUBLIC,
    )
    found: list[InviteMatch] = []
    seen: set[str] = set()
    for pattern in patterns:
        for m in pattern.finditer(text):
            raw = m.group(0)
            match = classify_invite_url(raw) or classify_invite_url(_ensure_https(raw))
            if not match:
                continue
            key = match.url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            found.append(match)
            if len(found) >= limit:
                return found
    return found


def resolve_href_invite(href: str, *, base_domain: str) -> InviteMatch | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    absolute = urljoin(f"https://{base_domain}", href)
    return classify_invite_url(absolute)


def invite_from_platform_page(website: str, platform: str | None, platform_id: str | None) -> InviteMatch | None:
    direct = classify_invite_url(website or "")
    if direct:
        return direct
    if not platform_id:
        return None
    platform_lc = (platform or "").lower()
    if platform_lc == "telegram":
        if platform_id.startswith("+") or platform_id.lower().startswith("joinchat"):
            return InviteMatch(url=f"https://t.me/{platform_id}", platform="telegram", rule="telegram_platform_id")
        if platform_id.lower() not in _TELEGRAM_BLOCKED and len(platform_id) >= 4:
            return InviteMatch(url=f"https://t.me/{platform_id}", platform="telegram", rule="telegram_platform_id")
    if platform_lc == "slack":
        # Only real invite URLs; bare workspace is not joinable.
        return None
    if platform_lc == "discord":
        return InviteMatch(url=f"https://discord.gg/{platform_id}", platform="discord", rule="discord_platform_id")
    if platform_lc == "whatsapp":
        return classify_invite_url(website or "")
    if platform_lc == "facebook":
        return classify_invite_url(website or "")
    if platform_lc == "linkedin":
        return classify_invite_url(website or "")
    if platform_lc == "skool":
        return InviteMatch(
            url=f"https://www.skool.com/{platform_id}",
            platform="skool",
            rule="skool_platform_id",
        )
    if platform_lc == "circle":
        if "." not in platform_id:
            return InviteMatch(
                url=f"https://{platform_id}.circle.so",
                platform="circle",
                rule="circle_platform_id",
            )
    return None


MEMBERS_PATTERNS = re.compile(
    r"([\d,.]+)\s*(members|member|people|subscribers|users|subscribers?)",
    re.I,
)
TG_SIZE_PATTERNS = re.compile(
    r"([\d\s,.]+)\s*(subscribers?|members?|online)",
    re.I,
)


def classify_telegram_page_kind(html: str) -> str:
    """Return 'group', 'channel', or 'unknown' from a public t.me page."""
    body = (html or "").lower()
    has_subscribers = "subscriber" in body
    has_members = bool(re.search(r"\bmembers?\b", body))
    if "go to channel" in body or "telegram channel" in body:
        return "channel"
    if has_subscribers and not has_members:
        return "channel"
    if has_members and not has_subscribers:
        return "group"
    if "join group" in body or "group chat" in body or ("view in telegram" in body and has_members):
        return "group"
    return "unknown"


def parse_member_count(text: str) -> tuple[int | None, str | None]:
    if not text:
        return None, None
    for pattern in (TG_SIZE_PATTERNS, MEMBERS_PATTERNS):
        for m in pattern.finditer(text):
            raw = m.group(1)
            digits = re.sub(r"[^\d]", "", raw)
            if not digits:
                continue
            try:
                n = int(digits)
            except ValueError:
                continue
            if n < 2 or n > 50_000_000:
                continue
            return n, m.group(0).strip()
    return None, None


def enrich_invite_page(join_url: str, *, timeout_seconds: float = 8.0) -> dict:
    """Fetch invite page for title + subscriber count (+ Discord API counts)."""
    import httpx

    out: dict = {"ok": False, "url": join_url}
    try:
        headers = {
            "User-Agent": "WarmrCommunityScanner/0.1 (+https://github.com/warmr-dev/warmr_comunity_scaner)"
        }
        invite = classify_invite_url(join_url)
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
            verify=False,
        ) as client:
            # Discord public invite API gives reliable member counts.
            if invite and invite.platform == "discord":
                m = re.search(r"(?:discord\.gg|discord\.com/invite)/([A-Za-z0-9_-]+)", join_url, re.I)
                if m:
                    api = client.get(
                        f"https://discord.com/api/v9/invites/{m.group(1)}",
                        params={"with_counts": "true"},
                    )
                    if api.status_code < 400:
                        data = api.json() if api.content else {}
                        guild = data.get("guild") or {}
                        out["ok"] = True
                        out["status_code"] = api.status_code
                        out["name"] = guild.get("name")
                        size = data.get("approximate_member_count")
                        if size:
                            out["size_members"] = int(size)
                            out["size_text"] = f"{size} members"
                        return out

            resp = client.get(join_url)
            out["status_code"] = resp.status_code
            if resp.status_code >= 400:
                return out
            html = resp.text or ""
        out["ok"] = True
        name = None
        m = re.search(
            r'class="tgme_page_title[^"]*"[^>]*>\s*<span[^>]*>([^<]+)',
            html,
            flags=re.I,
        )
        if m:
            name = m.group(1).strip()
        if not name:
            m = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
            if m:
                name = re.sub(r"\s*[|\-–].*$", "", m.group(1)).strip() or None
        size, size_text = parse_member_count(html)
        out["name"] = name
        out["size_members"] = size
        out["size_text"] = size_text
        # Skool / Circle often show "$9/mo" style pricing in HTML.
        price = re.search(
            r"\$\s*([0-9]{1,5}(?:\.[0-9]{1,2})?)\s*(?:/\s*(?:mo|month)|per\s*month)",
            html,
            flags=re.I,
        )
        if price:
            try:
                out["price_amount"] = float(price.group(1))
                out["price_text"] = price.group(0).strip()
                out["currency"] = "USD"
            except ValueError:
                pass
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:200]
        return out


def invite_host_ok(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(
        x in host
        for x in (
            "slack.com",
            "whatsapp.com",
            "wa.me",
            "skool.com",
            "circle.so",
            "facebook.com",
            "linkedin.com",
            "t.me",
            "telegram.me",
            "discord.gg",
            "discord.com",
        )
    )
