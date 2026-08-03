from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from community_scanner.models import NormalizedUrl, Platform

BLOCKED_DOMAINS = {
    "google.com",
    "google.co.uk",
    "bing.com",
    "yahoo.com",
    "youtube.com",
    "youtu.be",
    "amazon.com",
    "wikipedia.org",
    "x.com",
    "twitter.com",
    "instagram.com",
}

# Shared platforms: many communities per domain → need platform_id
PLATFORM_HOSTS: dict[str, Platform] = {
    "discord.com": Platform.DISCORD,
    "discord.gg": Platform.DISCORD,
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
    # subdomain.skool.com etc.
    for host, platform in PLATFORM_HOSTS.items():
        if domain.endswith("." + host):
            return platform
    return Platform.CUSTOM


def extract_platform_id(platform: Platform, domain: str, path: str) -> str | None:
    parts = [p for p in path.split("/") if p]

    if platform == Platform.DISCORD:
        # discord.gg/<invite> or discord.com/invite/<invite>
        if domain == "discord.gg" and parts:
            return parts[0].split("?")[0]
        if "invite" in parts:
            idx = parts.index("invite")
            if idx + 1 < len(parts):
                return parts[idx + 1].split("?")[0]
        return parts[0] if parts else None

    if platform == Platform.SKOOL:
        return parts[0].split("?")[0] if parts else None

    if platform == Platform.CIRCLE:
        # often <slug>.circle.so or circle.so/c/<slug>
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
        # workspace.slack.com → workspace
        if domain.endswith(".slack.com") and domain != "slack.com":
            return domain.removesuffix(".slack.com")
        return parts[0] if parts else None

    if platform in {Platform.FACEBOOK, Platform.LINKEDIN}:
        return "/".join(parts[:2]) if parts else None

    return None


def build_canonical_key(platform: Platform, domain: str, platform_id: str | None) -> str:
    if platform != Platform.CUSTOM and platform_id:
        return f"{platform.value}:{platform_id.lower()}"
    return f"site:{domain}"


def normalize_url(url: str) -> NormalizedUrl:
    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parsed = urlparse(raw)
    domain = _strip_www(parsed.netloc.split("@")[-1].split(":")[0])
    path = parsed.path or "/"
    # drop trailing slash except root
    clean_path = path if path == "/" else path.rstrip("/")
    website = urlunparse(("https", domain if not parsed.netloc.startswith("www.") else "www." + domain, clean_path, "", "", ""))
    # prefer https + original host style without query/fragment
    host_for_website = _strip_www(parsed.netloc.split("@")[-1].split(":")[0])
    website = urlunparse(("https", host_for_website, clean_path, "", "", ""))

    platform = detect_platform(domain)
    platform_id = extract_platform_id(platform, domain, clean_path)
    canonical_key = build_canonical_key(platform, domain, platform_id)

    blocked = domain in BLOCKED_DOMAINS or any(domain.endswith("." + d) for d in BLOCKED_DOMAINS)
    reason = "blocked_domain" if blocked else None

    # shared platform without id → cannot safely dedupe as unique community
    if not blocked and platform != Platform.CUSTOM and not platform_id:
        blocked = True
        reason = "missing_platform_id"

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
