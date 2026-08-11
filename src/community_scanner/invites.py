from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

# Telegram + WhatsApp + Slack (Discord excluded).
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
    r"(?:https?://)?(?:chat\.whatsapp\.com|whatsapp\.com/channel)/([A-Za-z0-9_-]+)",
    re.I,
)
_TELEGRAM = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([A-Za-z0-9_-]+)",
    re.I,
)
_TELEGRAM_PUBLIC = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z][A-Za-z0-9_]{3,})/?(?:\d+)?(?:\?|$|[\"'\s<>])",
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
    """Return InviteMatch for Telegram / WhatsApp / Slack join links."""
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
        code = m.group(1)
        if "channel" in m.group(0).lower():
            return InviteMatch(
                url=f"https://www.whatsapp.com/channel/{code}",
                platform="whatsapp",
                rule="whatsapp_channel",
            )
        return InviteMatch(
            url=f"https://chat.whatsapp.com/{code}",
            platform="whatsapp",
            rule="whatsapp_chat_invite",
        )

    m = _TELEGRAM.search(url)
    if m:
        raw = _ensure_https(m.group(0))
        return InviteMatch(url=raw, platform="telegram", rule="telegram_invite")

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
    matches = find_all_invites_in_text(text)
    return matches[0] if matches else None


def find_all_invites_in_text(text: str, *, limit: int = 200) -> list[InviteMatch]:
    """Collect unique Telegram / WhatsApp / Slack invites from free text / HTML."""
    if not text:
        return []
    patterns = (
        _SLACK_JOIN,
        _SLACK_SHARED,
        _WHATSAPP_CHAT,
        _TELEGRAM,
        _SLACK_WORKSPACE,
        _TELEGRAM_PUBLIC,
    )
    found: list[InviteMatch] = []
    seen: set[str] = set()
    for pattern in patterns:
        for m in pattern.finditer(text):
            raw = m.group(0)
            match = classify_invite_url(raw) or classify_invite_url(_ensure_https(raw))
            if not match:
                continue
            key = match.url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            found.append(match)
            if len(found) >= limit:
                return found
    return found


def resolve_href_invite(href: str, *, base_domain: str) -> InviteMatch | None:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        return None
    absolute = urljoin(f"https://{base_domain}", href)
    return classify_invite_url(absolute)


def invite_from_platform_page(website: str, platform: str | None, platform_id: str | None) -> InviteMatch | None:
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
    if platform_lc == "slack":
        return InviteMatch(url=f"https://{platform_id}.slack.com", platform="slack", rule="slack_platform_id")
    if platform_lc == "whatsapp":
        return classify_invite_url(website or "")
    return None


MEMBERS_PATTERNS = re.compile(
    r"([\d,.]+)\s*(members|member|people|subscribers|users|subscribers?)",
    re.I,
)
# Telegram preview pages: "1 234 subscribers" / "12,345 members"
TG_SIZE_PATTERNS = re.compile(
    r"([\d\s,.]+)\s*(subscribers?|members?|online)",
    re.I,
)
MIN_MEMBERS_FOR_UPSERT = 100


def parse_member_count(text: str) -> tuple[int | None, str | None]:
    """Best-effort audience size from invite / channel preview HTML."""
    if not text:
        return None, None
    for pattern in (TG_SIZE_PATTERNS, MEMBERS_PATTERNS):
        for m in pattern.finditer(text):
            raw = m.group(1)
            digits = re.sub(r"[^\d]", "", raw)
            if not digits:
                continue
            try:
                n = int(digits)
            except ValueError:
                continue
            # Ignore years / tiny noise / absurd crawler junk
            if n < 2 or n > 50_000_000:
                continue
            return n, m.group(0).strip()
    return None, None


def enrich_invite_page(join_url: str, *, timeout_seconds: float = 8.0) -> dict:
    """Fetch invite landing page and pull title + subscriber/member count."""
    import httpx

    out: dict = {"ok": False, "url": join_url}
    try:
        headers = {
            "User-Agent": "WarmrCommunityScanner/0.1 (+https://github.com/warmr-dev/warmr_comunity_scaner)"
        }
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
            verify=False,
        ) as client:
            resp = client.get(join_url)
            out["status_code"] = resp.status_code
            if resp.status_code >= 400:
                return out
            html = resp.text or ""
        out["ok"] = True
        # Prefer Telegram preview title block, then <title>
        name = None
        m = re.search(
            r'class="tgme_page_title[^"]*"[^>]*>\s*<span[^>]*>([^<]+)',
            html,
            flags=re.I,
        )
        if m:
            name = m.group(1).strip()
        if not name:
            m = re.search(r"<title>([^<]+)</title>", html, flags=re.I)
            if m:
                name = re.sub(r"\s*[|\-–].*$", "", m.group(1)).strip() or None
        size, size_text = parse_member_count(html)
        out["name"] = name
        out["size_members"] = size
        out["size_text"] = size_text
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:200]
        return out


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
        )
    )
