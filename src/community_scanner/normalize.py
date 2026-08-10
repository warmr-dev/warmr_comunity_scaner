from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from community_scanner.models import NormalizedUrl, Platform

# Volume mode: only skip pure search engines / video hosts (not useful as communities).
# Everything else is kept and written to community_scanner (junk flagged later).
BLOCKED_DOMAINS = {
    "google.com",
    "google.co.uk",
    "bing.com",
    "yahoo.com",
    "duckduckgo.com",
    "youtube.com",
    "youtu.be",
    "baidu.com",
}

BLOCKED_HOST_SUBSTRINGS = (
    "google.",
    "bing.",
)

# Positive signals: URL/title/snippet should look like a community/association.
COMMUNITY_HINTS = re.compile(
    r"(community|communities|forum|forums|association|chapter|membership|"
    r"mastermind|peer\s*group|network|club|guild|society|alliance|"
    r"skool|circle\.so|mightynetworks|discord\.gg|/invite/|"
    r"slack\.com|t\.me/|facebook\.com/groups|linkedin\.com/groups)",
    re.I,
)

# Hard negative signals in title/snippet/url
JUNK_HINTS = re.compile(
    r"(definition|meaning|dictionary|thesaurus|payed\s+vs|paid\s+vs|"
    r"lorem\s+ipsum|placeholder\s+query|crossword|chemical\s+equation|"
    r"file\s+taxes|tax\s+software|best\s+restaurants|hotel|best\s+buy|"
    r"what\s+is\s+accounting|accounting\s+basics|cpa\s+exam)",
    re.I,
)

# Shared platforms: many communities per domain → need platform_id
PLATFORM_HOSTS: dict[str, Platform] = {
    "discord.com": Platform.DISCORD,
    "discord.gg": Platform.DISCORD,
    "discordapp.com": Platform.DISCORD,
    "skool.com": Platform.SKOOL,
    "circle.so": Platform.CIRCLE,
    "canny.io": Platform.UNKNOWN,
    "slack.com": Platform.SLACK,
    "t.me": Platform.TELEGRAM,
    "telegram.me": Platform.TELEGRAM,
    "mightynetworks.com": Platform.MIGHTY,
    "facebook.com": Platform.FACEBOOK,
    "linkedin.com": Platform.LINKEDIN,
}


def _strip_www(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def detect_platform(domain: str) -> Platform:
    if domain in PLATFORM_HOSTS:
        return PLATFORM_HOSTS[domain]
    for host, platform in PLATFORM_HOSTS.items():
        if domain.endswith("." + host):
            return platform
    return Platform.CUSTOM


def extract_platform_id(platform: Platform, domain: str, path: str) -> str | None:
    parts = [p for p in path.split("/") if p]

    if platform == Platform.DISCORD:
        if domain == "discord.gg" and parts:
            return parts[0].split("?")[0]
        if "invite" in parts:
            idx = parts.index("invite")
            if idx + 1 < len(parts):
                return parts[idx + 1].split("?")[0]
        if domain in {"discord.com", "discordapp.com"} and not parts:
            return None
        return parts[0] if parts else None

    if platform == Platform.SKOOL:
        if not parts or parts[0] in {"discovery", "about", "login", "signup"}:
            return None
        return parts[0].split("?")[0]

    if platform == Platform.CIRCLE:
        if domain.endswith("circle.so") and domain != "circle.so":
            return domain.removesuffix(".circle.so")
        if parts:
            if parts[0] == "c" and len(parts) > 1:
                return parts[1]
            return parts[0]
        return None

    if platform == Platform.TELEGRAM:
        if parts and parts[0] not in {"s", "joinchat"}:
            return parts[0].lstrip("+")
        if parts and parts[0] == "joinchat" and len(parts) > 1:
            return parts[1]
        return None

    if platform == Platform.SLACK:
        if domain.endswith(".slack.com") and domain != "slack.com":
            return domain.removesuffix(".slack.com")
        return parts[0] if parts else None

    if platform == Platform.MIGHTY:
        if not parts or parts[0] in {"about", "pricing", "login"}:
            return None
        return parts[0]

    if platform in {Platform.FACEBOOK, Platform.LINKEDIN}:
        if "groups" in parts:
            idx = parts.index("groups")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "/".join(parts[:2]) if parts else None

    return None


def build_canonical_key(platform: Platform, domain: str, platform_id: str | None) -> str:
    if platform != Platform.CUSTOM and platform_id:
        return f"{platform.value}:{platform_id.lower()}"
    return f"site:{domain}"


def _is_blocked_host(domain: str) -> bool:
    if domain in BLOCKED_DOMAINS or any(domain.endswith("." + d) for d in BLOCKED_DOMAINS):
        return True
    return any(s in domain for s in BLOCKED_HOST_SUBSTRINGS)


def looks_like_community(url: str, title: str | None = None, snippet: str | None = None) -> bool:
    """Cheap pre-fetch filter: keep community-like SERP hits only."""
    blob = " ".join(filter(None, [url, title or "", snippet or ""]))
    if JUNK_HINTS.search(blob):
        return False
    if COMMUNITY_HINTS.search(blob):
        return True
    host = _strip_www(urlparse(url if "://" in url else f"https://{url}").netloc)
    platform = detect_platform(host)
    return platform != Platform.CUSTOM


def normalize_url(url: str) -> NormalizedUrl:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parsed = urlparse(raw)
    domain = _strip_www(parsed.netloc.split("@")[-1].split(":")[0])
    path = parsed.path or "/"
    clean_path = path if path == "/" else path.rstrip("/")
    host_for_website = domain
    website = urlunparse(("https", host_for_website, clean_path, "", "", ""))

    platform = detect_platform(domain)
    platform_id = extract_platform_id(platform, domain, clean_path)
    # Volume: keep platform pages even without id (canonical falls back to site:domain)
    if platform != Platform.CUSTOM and not platform_id and clean_path not in {"", "/"}:
        platform_id = clean_path.strip("/").split("/")[0] or None
    canonical_key = build_canonical_key(platform, domain, platform_id)

    blocked = _is_blocked_host(domain)
    reason = "blocked_domain" if blocked else None

    return NormalizedUrl(
        original_url=url,
        website=website,
        canonical_domain=domain,
        platform=platform,
        platform_id=platform_id,
        canonical_key=canonical_key,
        is_blocked=blocked,
        block_reason=reason,
    )
