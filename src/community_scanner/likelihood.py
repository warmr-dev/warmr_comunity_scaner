"""Cheap community-likelihood heuristics for bulk URL candidates."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_HIGH = (
    re.compile(r"skool\.com/[a-z0-9-]{3,}/?(?:about)?(?:\?|$)", re.I),
    re.compile(r"join\.slack\.com/t/[a-z0-9_-]+/shared_invite/", re.I),
    re.compile(r"chat\.whatsapp\.com/[A-Za-z0-9_-]{10,}", re.I),
    re.compile(r"facebook\.com/groups/\d+", re.I),
    re.compile(r"linkedin\.com/groups/\d+", re.I),
    re.compile(r"reddit\.com/r/[A-Za-z0-9_]+/?(?:\?|$)", re.I),
    re.compile(r"circle\.so/[a-z0-9-]{3,}/?(?:\?|$)", re.I),
    re.compile(r"app\.geneva\.com/invite/", re.I),
)

_MEDIUM = (
    re.compile(r"skool\.com/[a-z0-9-]{3,}", re.I),
    re.compile(r"join\.slack\.com/t/", re.I),
    re.compile(r"facebook\.com/groups/", re.I),
    re.compile(r"linkedin\.com/groups/", re.I),
    re.compile(r"mightynetworks\.com/", re.I),
    re.compile(r"/categories\.json$", re.I),
    re.compile(r"thehiveindex\.com/communities/", re.I),
)

_LOW_PATHS = {
    "",
    "/",
    "/blog",
    "/pricing",
    "/about",
    "/login",
    "/signup",
    "/careers",
    "/privacy",
    "/terms",
    "/robots.txt",
}

_NOISE_HOST_SUFFIXES = (
    "google.com",
    "youtube.com",
    "wikipedia.org",
    "amazon.com",
    "apple.com",
)


def community_likelihood(url: str, *, title: str | None = None, snippet: str | None = None) -> float:
    raw = (url or "").strip()
    if not raw:
        return 0.0
    lower = raw.lower()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"

    if any(host == s or host.endswith("." + s) for s in _NOISE_HOST_SUFFIXES):
        return 0.05
    if path.lower() in _LOW_PATHS and "invite" not in lower:
        # Marketing homepages are weak community signals.
        if host in {"circle.so", "skool.com", "mightynetworks.com", "geneva.com"}:
            return 0.15

    score = 0.35
    for pattern in _HIGH:
        if pattern.search(raw):
            score = max(score, 0.92)
            break
    else:
        for pattern in _MEDIUM:
            if pattern.search(raw):
                score = max(score, 0.7)
                break

    blob = f"{title or ''} {snippet or ''}".lower()
    if any(tok in blob for tok in ("community", "members", "join", "forum", "membership", "slack")):
        score = min(1.0, score + 0.08)
    if any(tok in blob for tok in ("career", "job board", "hiring", "wikipedia")):
        score = max(0.1, score - 0.25)
    return round(score, 3)
