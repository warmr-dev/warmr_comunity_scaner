from __future__ import annotations

import re
from urllib.parse import urlparse

# Reject Russian / Cyrillic content; allow all other languages.
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")

RU_HANDLE_SUFFIX_RE = re.compile(r"_(?:ru|su)$", re.I)

HTML_LANG_RU_RE = re.compile(
    r'\blang=["\'](?:ru|uk|be|kk|uz|ky|mo|tt|ba|ce|cv|av|os|sah|tyv|kbd|ady|krc|inh|che|mdf|myv|udm|koi|chm|mns|kum|nog|alt|bak|krc|kum|krc)',
    re.I,
)

RUSSIAN_HANDLE_TOKENS = frozenset(
    {
        "novosti",
        "russia",
        "moscow",
        "moskva",
        "piter",
        "spb",
        "rus",
        "rossiya",
        "россия",
        "новости",
        "москва",
    }
)

# Official / generic handles that are not niche IT communities.
OFFICIAL_JUNK_HANDLES = frozenset(
    {
        "telegram",
        "desktop",
        "download",
        "developers",
        "discord",
        "openai",
        "whatsapp",
        "telegramtips",
        "durov",
        "tgstat",
        "twitter",
        "youtube",
        "instagram",
        "facebook",
        "reddit",
        "github",
        "google",
        "apple",
        "microsoft",
        "android",
        "iphone",
        "macos",
        "windows",
        "linux",
        "vpn",
        "proxy",
        "bot",
        "news",
        "official",
        "support",
        "help",
        "admin",
    }
)


def contains_cyrillic(text: str) -> bool:
    return bool(text and CYRILLIC_RE.search(text))


def is_russian_tgstat_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return bool(host) and (host.endswith("tgstat.ru") or host == "tgstat.ru")


def normalize_tgstat_channel_url(url: str) -> str:
    """Normalize tgstat.ru mirror links to tgstat.com (still filtered separately)."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    if "tgstat.ru" in host:
        path = re.sub(r"^/en", "", path, flags=re.I)
        return f"https://tgstat.com{path}"
    return url.split("?")[0]


def is_official_junk_handle(platform_id: str | None) -> bool:
    if not platform_id:
        return False
    handle = platform_id.strip().lstrip("@").lower()
    if handle in OFFICIAL_JUNK_HANDLES:
        return True
    if handle.endswith("bot") and "novosti" in handle:
        return True
    return False


def is_russian_content(*parts: str | None) -> bool:
    blob = " ".join(str(p) for p in parts if p).strip()
    if not blob:
        return False
    if contains_cyrillic(blob):
        return True
    if HTML_LANG_RU_RE.search(blob):
        return True
    return False


def is_russian_handle(platform_id: str | None) -> bool:
    if not platform_id:
        return False
    pid = platform_id.strip().lstrip("@").lower()
    if RU_HANDLE_SUFFIX_RE.search(pid):
        return True
    tokens = re.split(r"[\W_]+", pid)
    return any(t in RUSSIAN_HANDLE_TOKENS for t in tokens if t)


def is_russian_community(
    *,
    name: str | None = None,
    url: str | None = None,
    platform_id: str | None = None,
    snippet: str | None = None,
    html: str | None = None,
    source_url: str | None = None,
) -> bool:
    """Return True when the row should be rejected as Russian-language content."""
    if source_url and is_russian_tgstat_url(source_url):
        return True
    if platform_id and is_russian_handle(platform_id):
        return True
    if platform_id and is_official_junk_handle(platform_id):
        return True
    if is_russian_content(name, snippet, html, url):
        return True
    return False


# Backward-compatible alias used across pipeline modules.
is_non_english_community = is_russian_community
is_non_english_content = is_russian_content
is_regional_tgstat_url = is_russian_tgstat_url
