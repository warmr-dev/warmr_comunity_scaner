from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Direct invite / group-join URL patterns only — never bare marketing pages.
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
    r"(?:https?://)?(?:chat\.whatsapp\.com|whatsapp\.com/channel)/[A-Za-z0-9_-]+",
    re.I,
)
_TELEGRAM = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)[A-Za-z0-9_-]+",
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

_BARE_SLACK = re.compile(r"^https?://(?:www\.)?slack\.com/?$", re.I)
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
}


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
    """Return InviteMatch if URL is a direct group/chat invite join link."""
    url = _normalize_candidate(url)
    if not url:
        return None
    if _BARE_SLACK.match(url):
        return None

    m = _SLACK_JOIN.search(url) or _SLACK_SHARED.search(url)
    if m:
        return InviteMatch(url=_ensure_https(m.group(0)), platform="slack", rule="slack_shared_invite")

    m = _SLACK_WORKSPACE.match(url) or _SLACK_WORKSPACE.search(url + " ")
    if m:
        slug = m.group(1).lower()
        if slug in {"app", "api", "status", "slack", "www", "get", "help", "join"}:
            return None
        return InviteMatch(
            url=f"https://{slug}.slack.com",
            platform="slack",
            rule="slack_workspace",
        )

    m = _WHATSAPP_CHAT.search(url)
    if m:
        return InviteMatch(url=_ensure_https(m.group(0)), platform="whatsapp", rule="whatsapp_chat_invite")

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
        code = m.group(1)
        return InviteMatch(url=f"https://discord.gg/{code}", platform="discord", rule="discord_invite")

    return None


def find_invite_in_text(text: str) -> InviteMatch | None:
    """Scan free text / HTML for the first valid invite URL."""
    if not text:
        return None
    patterns = (
        _SLACK_JOIN,
        _SLACK_SHARED,
        _WHATSAPP_CHAT,
        _TELEGRAM,
        _DISCORD,
        _SLACK_WORKSPACE,
        _TELEGRAM_PUBLIC,
    )
    for pattern in patterns:
        m = pattern.search(text)
        if not m:
            continue
        raw = m.group(0)
        # Discord capture group is just the code when using group(0) for full match — OK
        match = classify_invite_url(raw if "://" in raw or raw.lower().startswith(("discord.", "t.me", "chat.", "join.", "telegram.")) else raw)
        if match:
            return match
        # Fallback for patterns that need https prefix
        match = classify_invite_url(_ensure_https(raw))
        if match:
            return match
    return None


def resolve_href_invite(href: str, *, base_domain: str) -> InviteMatch | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    absolute = urljoin(f"https://{base_domain}", href)
    return classify_invite_url(absolute)


def invite_from_platform_page(website: str, platform: str | None, platform_id: str | None) -> InviteMatch | None:
    """If normalized URL is already an invite platform page with an id, treat as join_url."""
    direct = classify_invite_url(website or "")
    if direct:
        return direct
    if not platform_id:
        return None
    platform_lc = (platform or "").lower()
    if platform_lc == "discord":
        return InviteMatch(url=f"https://discord.gg/{platform_id}", platform="discord", rule="discord_platform_id")
    if platform_lc == "telegram":
        if platform_id.startswith("+") or platform_id.lower().startswith("joinchat"):
            return InviteMatch(url=f"https://t.me/{platform_id}", platform="telegram", rule="telegram_platform_id")
        if platform_id.lower() not in _TELEGRAM_BLOCKED and len(platform_id) >= 4:
            return InviteMatch(url=f"https://t.me/{platform_id}", platform="telegram", rule="telegram_platform_id")
    if platform_lc == "slack" and platform_id:
        return InviteMatch(url=f"https://{platform_id}.slack.com", platform="slack", rule="slack_platform_id")
    return None


def invite_host_ok(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(
        x in host
        for x in (
            "slack.com",
            "whatsapp.com",
            "wa.me",
            "t.me",
            "telegram.me",
            "discord.gg",
            "discord.com",
        )
    )
