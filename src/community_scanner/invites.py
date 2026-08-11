from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Direct invite / group-join URL patterns only — never bare marketing pages.
_SLACK_SHARED = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?slack\.com/(?:shared_invite/[A-Za-z0-9_-]+|ssb/redirect)",
    re.I,
)
_SLACK_JOIN = re.compile(
    r"https?://join\.slack\.com/t/[A-Za-z0-9_-]+(?:/[^\s\"'<>]*)?",
    re.I,
)
_SLACK_WORKSPACE = re.compile(
    r"https?://([a-z0-9][a-z0-9-]{1,62})\.slack\.com(?:/|$|\?)",
    re.I,
)
_WHATSAPP_CHAT = re.compile(
    r"https?://(?:chat\.whatsapp\.com|whatsapp\.com/channel)/[A-Za-z0-9_-]+",
    re.I,
)
_TELEGRAM = re.compile(
    r"https?://(?:t\.me|telegram\.me)/(?:\+|joinchat/)[A-Za-z0-9_-]+",
    re.I,
)
_TELEGRAM_PUBLIC = re.compile(
    r"https?://(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,})/?(?:\d+)?(?:\?|$)",
    re.I,
)
_DISCORD = re.compile(
    r"https?://(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9_-]+",
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


def _normalize_candidate(url: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
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
        return InviteMatch(url=m.group(0), platform="slack", rule="slack_shared_invite")

    m = _SLACK_WORKSPACE.match(url)
    if m:
        slug = m.group(1).lower()
        if slug in {"app", "api", "status", "slack", "www", "get", "help"}:
            return None
        # Workspace root is a usable join destination (Warmr etalon style).
        return InviteMatch(
            url=f"https://{slug}.slack.com",
            platform="slack",
            rule="slack_workspace",
        )

    m = _WHATSAPP_CHAT.search(url)
    if m:
        return InviteMatch(url=m.group(0), platform="whatsapp", rule="whatsapp_chat_invite")

    m = _TELEGRAM.search(url)
    if m:
        return InviteMatch(url=m.group(0), platform="telegram", rule="telegram_invite")

    m = _TELEGRAM_PUBLIC.match(url)
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
        return InviteMatch(url=m.group(0), platform="discord", rule="discord_invite")

    return None


def find_invite_in_text(text: str) -> InviteMatch | None:
    """Scan free text / HTML for the first valid invite URL."""
    if not text:
        return None
    # Prefer stronger invite shapes first.
    patterns = (
        (_SLACK_JOIN, "slack", "slack_shared_invite"),
        (_SLACK_SHARED, "slack", "slack_shared_invite"),
        (_WHATSAPP_CHAT, "whatsapp", "whatsapp_chat_invite"),
        (_TELEGRAM, "telegram", "telegram_invite"),
        (_DISCORD, "discord", "discord_invite"),
        (_SLACK_WORKSPACE, "slack", "slack_workspace"),
        (_TELEGRAM_PUBLIC, "telegram", "telegram_public"),
    )
    for pattern, platform, rule in patterns:
        m = pattern.search(text)
        if not m:
            continue
        match = classify_invite_url(m.group(0))
        if match:
            return match
        # Telegram public / workspace need classify side-filters
        if platform == "telegram" and rule == "telegram_public":
            continue
        if platform == "slack" and rule == "slack_workspace":
            continue
    return None


def resolve_href_invite(href: str, *, base_domain: str) -> InviteMatch | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    absolute = urljoin(f"https://{base_domain}", href)
    return classify_invite_url(absolute)


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
