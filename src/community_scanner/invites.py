from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Telegram + WhatsApp only (Discord/Slack intentionally excluded).
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
    """Return InviteMatch for Telegram/WhatsApp join/channel links only."""
    url = _normalize_candidate(url)
    if not url:
        return None

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

    return None


def find_invite_in_text(text: str) -> InviteMatch | None:
    """Scan free text / HTML for the first Telegram/WhatsApp invite URL."""
    if not text:
        return None
    patterns = (
        _WHATSAPP_CHAT,
        _TELEGRAM,
        _TELEGRAM_PUBLIC,
    )
    for pattern in patterns:
        m = pattern.search(text)
        if not m:
            continue
        raw = m.group(0)
        match = classify_invite_url(raw)
        if match:
            return match
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
    """If normalized URL is already a Telegram/WhatsApp page with an id, treat as join_url."""
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
    if platform_lc == "whatsapp":
        return classify_invite_url(website or "")
    return None


def invite_host_ok(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(
        x in host
        for x in (
            "whatsapp.com",
            "wa.me",
            "t.me",
            "telegram.me",
        )
    )
