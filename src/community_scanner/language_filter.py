from __future__ import annotations

import re
from urllib.parse import urlparse

# Non-English scripts — primary filter (Russian/Cyrillic, CJK, Arabic, etc.).
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF\u0500-\u052F]")
CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

NON_EN_HANDLE_SUFFIX_RE = re.compile(
    r"_(?:ru|su|ua|kz|by|uz|es|fr|de|it|pt|pl|tr|ar|cn|jp|kr|hi|bn|fa|id|vi|th|"
    r"cs|sk|ro|hu|nl|se|no|dk|fi|gr|bg|hr|sr|sl|lt|lv|ee|mx|br|co|cl|pe|ve)$",
    re.I,
)

HTML_LANG_NON_EN_RE = re.compile(
    r'\blang=["\'](?:ru|uk|be|kk|uz|es|fr|de|it|pt|pl|tr|ar|zh|ja|ko|hi|bn|fa|he|th|vi|id|cs|sk|ro|hu|nl|sv|no|da|fi|el|bg|hr|sr|sl|lt|lv|et)',
    re.I,
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

REGIONAL_TGSTAT_HOSTS = re.compile(
    r"^(?:uk|uz|kz|by|ua|de|fr|es|it|tr|ir|in|id|br|mx|cn|jp|kr)\.tgstat\.",
    re.I,
)


def contains_non_latin_script(text: str) -> bool:
    if not text:
        return False
    return bool(
        CYRILLIC_RE.search(text)
        or CJK_RE.search(text)
        or ARABIC_RE.search(text)
        or HEBREW_RE.search(text)
        or THAI_RE.search(text)
        or DEVANAGARI_RE.search(text)
    )


def is_regional_tgstat_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    if not host:
        return False
    if host.endswith("tgstat.ru") or host == "tgstat.ru":
        return True
    return bool(REGIONAL_TGSTAT_HOSTS.match(host))


def normalize_tgstat_channel_url(url: str) -> str:
    """Prefer tgstat.com over regional / .ru mirrors."""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    if "tgstat.ru" in host or REGIONAL_TGSTAT_HOSTS.match(host):
        path = re.sub(r"^/en", "", path, flags=re.I)
        return f"https://tgstat.com{path}"
    return url.split("?")[0]


def is_official_junk_handle(platform_id: str | None) -> bool:
    if not platform_id:
        return False
    handle = platform_id.strip().lstrip("@").lower()
    if handle in OFFICIAL_JUNK_HANDLES:
        return True
    if handle.endswith("bot") and any(
        x in handle
        for x in ("lavoro", "travail", "empleo", "arbeit", "novosti", "новости")
    ):
        return True
    return False


def is_english_text(text: str | None) -> bool:
    """Heuristic: ASCII/Latin-only visible text."""
    if not text or not str(text).strip():
        return True
    blob = str(text).strip()
    if contains_non_latin_script(blob):
        return False
    letters = [c for c in blob if c.isalpha()]
    if not letters:
        return True
    ascii_letters = sum(1 for c in letters if ord(c) < 128)
    return (ascii_letters / len(letters)) >= 0.9


def is_non_english_content(*parts: str | None) -> bool:
    blob = " ".join(str(p) for p in parts if p).strip()
    if not blob:
        return False
    if contains_non_latin_script(blob):
        return True
    if HTML_LANG_NON_EN_RE.search(blob):
        return True
    return False


def is_non_english_community(
    *,
    name: str | None = None,
    url: str | None = None,
    platform_id: str | None = None,
    snippet: str | None = None,
    html: str | None = None,
    source_url: str | None = None,
) -> bool:
    """Return True when the row should be rejected for non-English language."""
    if source_url and is_regional_tgstat_url(source_url):
        return True
    if platform_id:
        pid = platform_id.strip().lstrip("@")
        if NON_EN_HANDLE_SUFFIX_RE.search(pid):
            return True
        if is_official_junk_handle(pid):
            return True
    if is_non_english_content(name, snippet, html, url):
        return True
    if name and not is_english_text(name):
        return True
    return False
