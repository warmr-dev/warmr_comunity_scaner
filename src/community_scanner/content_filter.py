from __future__ import annotations

import re

# Adult / 18+ / NSFW — applied before upsert across SERP, fetch, and directory crawl.
ADULT_CONTENT_RE = re.compile(
    r"(?:"
    r"18\+|18\s*plus|\+18|adults?\s*only|for\s*adults|"
    r"nsfw|not\s*safe\s*for\s*work|"
    r"porn(?:o|hub|ography)?|xxx|\bsex\b|sexchat|sexting|"
    r"erotic|erotica|onlyfans|fansly|"
    r"hentai|lewd|nude|naked|strip(?:per|club)|"
    r"escort|camgirl|cam\s*girl|bdsm|fetish|"
    r"пorno|порно|эротик|интим|для\s*взрослых|"
    r"mature\s*content|adult\s*content|18\s*\+"
    r")",
    re.I,
)

ADULT_HANDLE_RE = re.compile(
    r"(?:^|[\W_])(?:"
    r"porn|xxx|nsfw|adult|onlyfans|fansly|hentai|nude|naked|"
    r"sexchat|erotic|escort|camgirl|bdsm|fetish|lewd"
    r")(?:$|[\W_])",
    re.I,
)

# tgstat / directory category labels
ADULT_CATEGORY_RE = re.compile(
    r"(?:category|tag|topic)[^<]{0,40}(?:erotica|adult|18\+|porn|nsfw|sex)",
    re.I,
)


def is_adult_content(*parts: str | None) -> bool:
    """Return True when any text fragment looks like 18+ / NSFW content."""
    blob = " ".join(str(p) for p in parts if p).strip()
    if not blob:
        return False
    if ADULT_CONTENT_RE.search(blob):
        return True
    if ADULT_CATEGORY_RE.search(blob):
        return True
    return False


def is_adult_platform_id(platform_id: str | None) -> bool:
    if not platform_id:
        return False
    handle = platform_id.strip().lstrip("@").lower()
    if not handle:
        return False
    if ADULT_HANDLE_RE.search(handle):
        return True
    tokens = re.split(r"[\W_]+", handle)
    adult_tokens = {
        "porn",
        "porno",
        "xxx",
        "nsfw",
        "adult",
        "onlyfans",
        "fansly",
        "hentai",
        "nude",
        "naked",
        "sex",
        "sexchat",
        "erotic",
        "escort",
        "camgirl",
        "bdsm",
        "fetish",
        "lewd",
    }
    return any(t in adult_tokens for t in tokens if t)


def is_adult_community(
    *,
    name: str | None = None,
    url: str | None = None,
    platform_id: str | None = None,
    snippet: str | None = None,
    html: str | None = None,
) -> bool:
    """Unified gate for invite rows and discovery hits."""
    if is_adult_platform_id(platform_id):
        return True
    return is_adult_content(name, url, platform_id, snippet, html)
