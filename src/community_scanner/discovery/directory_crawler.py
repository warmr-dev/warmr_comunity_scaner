from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from community_scanner.content_filter import is_adult_community
from community_scanner.language_filter import (
    is_non_english_community,
    is_regional_tgstat_url,
    normalize_tgstat_channel_url,
)
from community_scanner.discovery.base import DiscoveryProvider, QueryParams
from community_scanner.invites import (
    MIN_MEMBERS_FOR_UPSERT,
    classify_invite_url,
    find_all_invites_in_text,
    parse_member_count,
)
from community_scanner.models import DiscoveryHit

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# tgstat tags use short slugs; map long PIPE_NICHES names to tag pages that exist.
NICHE_TAG_ALIASES: dict[str, str] = {
    "software-engineering": "programming",
    "machine-learning": "python",
    "data-science": "python",
    "data-engineering": "python",
    "cloud-computing": "devops",
    "web-development": "javascript",
    "mobile-development": "programming",
    "computer-science": "programming",
    "online-learning": "education",
    "ai-founders": "startup",
    "open-source": "programming",
    "coding": "programming",
    "developers": "programming",
    "tech": "programming",
    "edtech": "education",
    "bootcamp": "programming",
    "devtools": "programming",
    "mlops": "devops",
    "cybersecurity": "security",
}

TGSTAT_CHANNEL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?tgstat\.(?:com|ru)(?:/en)?/channel/(@[A-Za-z0-9_]+)",
    re.I,
)
TGSTAT_SUBSCRIBER_RE = re.compile(
    r">([\d\s,.]+)</h2>\s*<div[^>]*>\s*subscribers",
    re.I,
)
DISBOARD_SERVER_RE = re.compile(
    r'href="(/server/join/\d+[^"]*)"[^>]*>([^<]{2,120})',
    re.I,
)


@dataclass(frozen=True)
class DirectoryEntry:
    invite_url: str
    title: str | None
    size_members: int | None
    size_text: str | None
    source_url: str
    site: str


def niche_to_tag(niche: str) -> str:
    raw = (niche or "programming").strip().lower()
    return NICHE_TAG_ALIASES.get(raw, raw.replace("_", "-"))


def _http_get(url: str, *, timeout: float, delay: float) -> str | None:
    if delay > 0:
        time.sleep(delay)
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            verify=False,
        ) as client:
            resp = client.get(url)
            if resp.status_code >= 400:
                return None
            return resp.text or ""
    except Exception as exc:  # noqa: BLE001
        log.debug("directory fetch failed %s: %s", url, exc)
        return None


def extract_tgstat_channel_urls(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in TGSTAT_CHANNEL_RE.finditer(html or ""):
        url = match.group(0).split("?")[0]
        url = re.sub(r"/stat$", "", url, flags=re.I)
        url = normalize_tgstat_channel_url(url)
        if is_regional_tgstat_url(url):
            continue
        key = url.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(url)
    return found


def parse_tgstat_subscribers(html: str) -> tuple[int | None, str | None]:
    match = TGSTAT_SUBSCRIBER_RE.search(html or "")
    if not match:
        return parse_member_count(html or "")
    raw = match.group(1)
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        return None, None
    try:
        value = int(digits)
    except ValueError:
        return None, None
    if value < 2:
        return None, None
    return value, f"{raw.strip()} subscribers"


def tgstat_username_from_url(url: str) -> str | None:
    match = re.search(r"/channel/(@[A-Za-z0-9_]+)", url, flags=re.I)
    return match.group(1) if match else None


def primary_telegram_invite(html: str, username: str) -> str | None:
    handle = username.lstrip("@").lower()
    for invite in find_all_invites_in_text(html):
        if invite.platform != "telegram":
            continue
        tail = invite.url.rstrip("/").rsplit("/", 1)[-1].lower()
        if tail == handle:
            return invite.url
    if handle and handle not in {"share", "joinchat"}:
        return f"https://t.me/{username.lstrip('@')}"
    return None


def crawl_tgstat(
    niche: str,
    *,
    max_channels: int,
    timeout: float,
    delay: float,
) -> list[DirectoryEntry]:
    tag = niche_to_tag(niche)
    listing_urls = [
        f"https://tgstat.com/en/tag/{tag}",
    ]

    channel_urls: list[str] = []
    seen_channels: set[str] = set()
    for listing_url in listing_urls:
        html = _http_get(listing_url, timeout=timeout, delay=delay)
        if not html:
            continue
        for url in extract_tgstat_channel_urls(html):
            key = url.lower()
            if key in seen_channels:
                continue
            seen_channels.add(key)
            channel_urls.append(url)
        if len(channel_urls) >= max_channels:
            break

    entries: list[DirectoryEntry] = []
    for channel_url in channel_urls[:max_channels]:
        html = _http_get(channel_url, timeout=timeout, delay=delay)
        if not html:
            continue
        username = tgstat_username_from_url(channel_url)
        if not username:
            continue
        invite_url = primary_telegram_invite(html, username)
        if not invite_url:
            continue
        if not classify_invite_url(invite_url):
            continue

        size, size_text = parse_tgstat_subscribers(html)
        title_match = re.search(
            r'class="[^"]*font-24[^"]*"[^>]*>([^<]+)',
            html,
            flags=re.I,
        )
        title = title_match.group(1).strip() if title_match else username.lstrip("@")

        if is_adult_community(
            name=title,
            url=invite_url,
            platform_id=username.lstrip("@"),
            html=html,
        ):
            continue

        if is_non_english_community(
            name=title,
            url=invite_url,
            platform_id=username.lstrip("@"),
            html=html,
            source_url=channel_url,
        ):
            continue

        entries.append(
            DirectoryEntry(
                invite_url=invite_url,
                title=title,
                size_members=size,
                size_text=size_text,
                source_url=channel_url,
                site="tgstat",
            )
        )
    return entries


def crawl_disboard(
    niche: str,
    *,
    max_channels: int,
    timeout: float,
    delay: float,
) -> list[DirectoryEntry]:
    tag = niche_to_tag(niche)
    search_urls = [
        f"https://disboard.org/search?keyword={tag}&page={page}"
        for page in range(1, 4)
    ]
    entries: list[DirectoryEntry] = []
    seen: set[str] = set()

    for search_url in search_urls:
        html = _http_get(search_url, timeout=timeout, delay=delay)
        if not html:
            continue
        for match in DISBOARD_SERVER_RE.finditer(html):
            path, title = match.group(1), match.group(2).strip()
            page_url = urljoin("https://disboard.org", path)
            page_html = _http_get(page_url, timeout=timeout, delay=delay)
            if not page_html:
                continue
            invites = find_all_invites_in_text(page_html)
            discord = next((i for i in invites if i.platform == "discord"), None)
            if not discord:
                continue
            key = discord.url.lower()
            if key in seen:
                continue
            seen.add(key)
            size, size_text = parse_member_count(page_html)
            if is_adult_community(name=title, url=discord.url, html=page_html):
                continue
            if is_non_english_community(name=title, url=discord.url, html=page_html, source_url=page_url):
                continue
            entries.append(
                DirectoryEntry(
                    invite_url=discord.url,
                    title=title,
                    size_members=size,
                    size_text=size_text,
                    source_url=page_url,
                    site="disboard",
                )
            )
            if len(entries) >= max_channels:
                return entries
    return entries


def crawl_discordservers(
    niche: str,
    *,
    max_channels: int,
    timeout: float,
    delay: float,
) -> list[DirectoryEntry]:
    tag = niche_to_tag(niche)
    html = _http_get(f"https://discordservers.com/search/{tag}", timeout=timeout, delay=delay)
    if not html:
        return []

    server_paths = []
    seen_paths: set[str] = set()
    for match in re.finditer(r'href="(/server/\d+)"', html):
        path = match.group(1)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        server_paths.append(path)

    entries: list[DirectoryEntry] = []
    seen_invites: set[str] = set()
    for path in server_paths[: max_channels * 2]:
        page_url = urljoin("https://discordservers.com", path)
        page_html = _http_get(page_url, timeout=timeout, delay=delay)
        if not page_html:
            continue
        invites = [
            i
            for i in find_all_invites_in_text(page_html)
            if i.platform == "discord"
            and not i.url.rstrip("/").lower().endswith("/servers")
            and "projectslayers" not in i.url.lower()
        ]
        if not invites:
            continue
        invite = invites[0]
        key = invite.url.lower()
        if key in seen_invites:
            continue
        seen_invites.add(key)

        title_match = re.search(r"<title>([^<|]+)", page_html, flags=re.I)
        title = title_match.group(1).strip() if title_match else tag
        size, size_text = parse_member_count(page_html)

        if is_adult_community(name=title, url=invite.url, html=page_html):
            continue

        if is_non_english_community(name=title, url=invite.url, html=page_html, source_url=page_url):
            continue

        entries.append(
            DirectoryEntry(
                invite_url=invite.url,
                title=title,
                size_members=size,
                size_text=size_text,
                source_url=page_url,
                site="discordservers",
            )
        )
        if len(entries) >= max_channels:
            break
    return entries


def entries_to_hits(entries: list[DirectoryEntry], *, niche: str, provider: str) -> list[DiscoveryHit]:
    hits: list[DiscoveryHit] = []
    for entry in entries:
        snippet_parts = [f"site={entry.site}", f"source={entry.source_url}"]
        if entry.size_text:
            snippet_parts.append(entry.size_text)
        elif entry.size_members is not None:
            snippet_parts.append(f"{entry.size_members} members")

        hits.append(
            DiscoveryHit(
                url=entry.invite_url,
                title=entry.title,
                snippet=" | ".join(snippet_parts),
                provider=provider,
                query=niche,
            )
        )
    return hits


class DirectoryCrawlerProvider(DiscoveryProvider):
    """Direct HTML crawl of community directories (tgstat, disboard, ...)."""

    name = "directory"

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        delay: float = 0.4,
        max_channels_per_site: int = 40,
        min_members: int = MIN_MEMBERS_FOR_UPSERT,
        sites: tuple[str, ...] = ("tgstat", "disboard", "discordservers"),
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.max_channels_per_site = max_channels_per_site
        self.min_members = min_members
        self.sites = sites

    def crawl(self, params: QueryParams, count: int = 100) -> list[DiscoveryHit]:
        niche = params.niche or "programming"
        per_site = max(5, min(self.max_channels_per_site, count // max(len(self.sites), 1) + 5))
        all_entries: list[DirectoryEntry] = []

        if "tgstat" in self.sites:
            try:
                all_entries.extend(
                    crawl_tgstat(
                        niche,
                        max_channels=per_site,
                        timeout=self.timeout,
                        delay=self.delay,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("tgstat crawl failed niche=%s: %s", niche, exc)

        if "disboard" in self.sites and len(all_entries) < count:
            try:
                all_entries.extend(
                    crawl_disboard(
                        niche,
                        max_channels=per_site,
                        timeout=self.timeout,
                        delay=self.delay,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("disboard crawl failed niche=%s: %s", niche, exc)

        if "discordservers" in self.sites and len(all_entries) < count:
            try:
                all_entries.extend(
                    crawl_discordservers(
                        niche,
                        max_channels=per_site,
                        timeout=self.timeout,
                        delay=self.delay,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("discordservers crawl failed niche=%s: %s", niche, exc)

        # Prefer known-large channels; keep unknown-size for pipeline enrich attempt.
        filtered: list[DirectoryEntry] = []
        seen_urls: set[str] = set()
        for entry in sorted(
            all_entries,
            key=lambda e: (e.size_members or 0),
            reverse=True,
        ):
            key = entry.invite_url.lower().rstrip("/")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            if entry.size_members is not None and entry.size_members < self.min_members:
                continue
            filtered.append(entry)
            if len(filtered) >= count:
                break

        return entries_to_hits(filtered, niche=niche, provider=self.name)

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        """Compatibility shim: derive niche from query tail."""
        niche = query
        if query.lower().startswith("site:"):
            parts = query.split(None, 1)
            niche = parts[1] if len(parts) > 1 else "programming"
        return self.crawl(QueryParams(niche=niche), count=count)


def directory_listing_fallback_hits(html: str, *, base_url: str, niche: str) -> list[DiscoveryHit]:
    """Return tgstat channel page hits when only listing HTML is available."""
    hits: list[DiscoveryHit] = []
    for url in extract_tgstat_channel_urls(html):
        if not url.startswith("http"):
            url = urljoin(base_url, url)
        hits.append(
            DiscoveryHit(
                url=url,
                title=urlparse(url).path.rsplit("/", 1)[-1],
                snippet=f"site=tgstat-listing niche={niche}",
                provider="directory-listing",
                query=niche,
            )
        )
    return hits
