"""Common Crawl CDX bulk discovery provider."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from community_scanner.discovery.base import DiscoveryProvider, QueryParams
from community_scanner.likelihood import community_likelihood
from community_scanner.models import DiscoveryHit
from community_scanner.paths import data_dir

log = logging.getLogger(__name__)

COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"

# Patterns tuned for mass inventory without Discord/Telegram primary.
DEFAULT_PATTERNS: tuple[str, ...] = (
    "*.skool.com/*",
    "*.circle.so/*",
    "join.slack.com/t/*",
    "chat.whatsapp.com/*",
    "*.mightynetworks.com/*",
    "www.facebook.com/groups/*",
    "facebook.com/groups/*",
    "www.linkedin.com/groups/*",
    "linkedin.com/groups/*",
    "old.reddit.com/r/*",
    "www.reddit.com/r/*",
    "reddit.com/r/*",
    "*.geneva.com/*",
    "groups.io/g/*",
    "www.meetup.com/*",
    "meetup.com/*",
    "*.discourse.group/*",
    "*.discourse.org/*",
    "forum.*/*",
)

_SKIP_SLUGS = {
    "discovery",
    "about",
    "login",
    "signup",
    "pricing",
    "blog",
    "help",
    "api",
    "settings",
    "explore",
    "search",
    "robots.txt",
    "careers",
    "privacy",
    "terms",
}


def _canonical_community_url(url: str) -> str | None:
    """Reduce noisy CDX URLs to a stable community landing URL."""
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    host = parsed.netloc.lower().removeprefix("www.")
    parts = [p for p in parsed.path.split("/") if p]
    if not host:
        return None

    if host.endswith("skool.com") and parts:
        slug = parts[0].lower()
        if slug in _SKIP_SLUGS:
            return None
        return f"https://www.skool.com/{slug}"

    if host.endswith("circle.so") and parts:
        slug = parts[0].lower()
        if slug in _SKIP_SLUGS | {"br", "ai", "academy", "affiliate-faqs", "brand"}:
            return None
        return f"https://{host}/{slug}"

    if host == "join.slack.com" and len(parts) >= 2 and parts[0] == "t":
        # Keep full invite when present; else workspace root.
        if "shared_invite" in parts:
            return f"https://join.slack.com{parsed.path}"
        return f"https://join.slack.com/t/{parts[1]}"

    if host == "chat.whatsapp.com" and parts:
        code = parts[0]
        if code.lower() in _SKIP_SLUGS:
            return None
        return f"https://chat.whatsapp.com/{code}"

    if "facebook.com" in host and len(parts) >= 2 and parts[0] == "groups":
        return f"https://www.facebook.com/groups/{parts[1]}"

    if "linkedin.com" in host and len(parts) >= 2 and parts[0] == "groups":
        return f"https://www.linkedin.com/groups/{parts[1]}"

    if "reddit.com" in host and len(parts) >= 2 and parts[0] == "r":
        return f"https://www.reddit.com/r/{parts[1]}"

    if host.endswith("geneva.com") and "invite" in parts:
        return f"https://{host}{parsed.path}"

    if host.endswith("mightynetworks.com") and parts:
        # Prefer community app paths when present.
        if parts[0] == "app" and len(parts) >= 2:
            return f"https://www.mightynetworks.com/app/{parts[1]}"
        if parts[0] not in _SKIP_SLUGS:
            return f"https://www.mightynetworks.com/{parts[0]}"

    if host.endswith("groups.io") and len(parts) >= 2 and parts[0] == "g":
        return f"https://groups.io/g/{parts[1]}"

    if host.endswith("meetup.com") and parts:
        slug = parts[0].lower()
        if slug not in _SKIP_SLUGS | {"find", "cities", "topics", "login", "register"}:
            return f"https://www.meetup.com/{parts[0]}"

    return None


def _resume_path() -> Path:
    return data_dir() / "commoncrawl_resume.json"


def _load_resume_state() -> dict:
    path = _resume_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_resume_state(state: dict) -> None:
    path = _resume_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _collinfo_cache_path() -> Path:
    return data_dir() / "commoncrawl_collinfo.json"


def _load_collinfo(client: httpx.Client) -> list[dict]:
    """Fetch collinfo with retries; fall back to on-disk cache."""
    cache = _collinfo_cache_path()
    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            resp = client.get(COLLINFO_URL)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                raise RuntimeError("Common Crawl collinfo.json returned empty list")
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(data), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = attempt * 1.8
            print(f"commoncrawl collinfo attempt={attempt} err={exc!s} sleep={wait:.1f}s", flush=True)
            time.sleep(wait)
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                print(f"commoncrawl collinfo using cache entries={len(data)}", flush=True)
                return data
        except Exception:  # noqa: BLE001
            pass
    raise RuntimeError(f"Common Crawl collinfo failed: {last_err}")


class CommonCrawlProvider(DiscoveryProvider):
    """Pull community-shaped URLs from Common Crawl CDX index."""

    name = "commoncrawl"

    def __init__(
        self,
        *,
        index: str = "latest",
        index_offset: int = 0,
        timeout: float = 45.0,
        delay_ms: int = 500,
        page_size: int = 400,
        max_pages_per_pattern: int = 25,
        min_likelihood: float = 0.45,
        persist_resume: bool = True,
        patterns: tuple[str, ...] | None = None,
    ) -> None:
        self.index = (index or "latest").strip()
        self.index_offset = max(0, int(index_offset or 0))
        self.timeout = timeout
        self.delay_ms = max(0, delay_ms)
        self.page_size = max(10, min(page_size, 1000))
        self.max_pages_per_pattern = max(0, max_pages_per_pattern)
        self.min_likelihood = min_likelihood
        self.persist_resume = persist_resume
        self.patterns = patterns or DEFAULT_PATTERNS
        self._cdx_api: str | None = None
        self._index_id: str | None = None

    def _pick_from_collinfo(self, data: list[dict], offset: int) -> tuple[str, str]:
        pick = data[offset % len(data)]
        cdx = pick.get("cdx-api")
        if not cdx:
            raise RuntimeError("Common Crawl collinfo missing cdx-api")
        index_id = str(pick.get("id") or cdx)
        return index_id, cdx

    def _resolve_cdx_api(self, client: httpx.Client) -> str:
        if self._cdx_api:
            return self._cdx_api
        if self.index != "latest" and self.index != "rotate" and self.index.startswith("CC-MAIN-"):
            self._index_id = self.index
            self._cdx_api = f"https://index.commoncrawl.org/{self.index}-index"
            return self._cdx_api
        if self.index.startswith("http"):
            self._cdx_api = self.index
            self._index_id = self.index
            return self._cdx_api

        data = _load_collinfo(client)
        # Prefer requested offset; on bad entry try a few neighbors.
        last_err: Exception | None = None
        for bump in range(0, min(8, len(data))):
            try:
                index_id, cdx = self._pick_from_collinfo(data, self.index_offset + bump)
                self._cdx_api = cdx
                self._index_id = index_id
                print(
                    f"commoncrawl using index={self._index_id} "
                    f"offset={self.index_offset + bump} cdx={cdx}",
                    flush=True,
                )
                return cdx
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        raise RuntimeError(f"Common Crawl index pick failed: {last_err}")

    def _fetch_page(
        self,
        client: httpx.Client,
        cdx_api: str,
        pattern: str,
        *,
        page: int = 0,
    ) -> list[dict]:
        # Page-based CDX pagination is more reliable than resumeKey across indexes.
        params = {
            "url": pattern,
            "output": "json",
            "fl": "url",
            "limit": str(self.page_size),
            "page": str(page),
        }
        for attempt in range(1, 4):
            try:
                resp = client.get(cdx_api, params=params)
                if resp.status_code in {429, 502, 503}:
                    wait = attempt * 1.5
                    print(
                        f"commoncrawl {resp.status_code} pattern={pattern!r} "
                        f"page={page} sleep={wait:.1f}s",
                        flush=True,
                    )
                    time.sleep(wait)
                    continue
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                rows: list[dict] = []
                for line in resp.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        if line.startswith("http"):
                            rows.append({"url": line})
                        continue
                    if isinstance(obj, dict) and obj.get("url"):
                        rows.append(obj)
                    elif isinstance(obj, str) and obj.startswith("http"):
                        rows.append({"url": obj})
                    elif isinstance(obj, list) and obj and isinstance(obj[0], str) and obj[0].startswith("http"):
                        rows.append({"url": obj[0]})
                return rows
            except httpx.HTTPError as exc:
                if attempt == 3:
                    log.warning("commoncrawl fetch failed pattern=%s: %s", pattern, exc)
                    return []
                time.sleep(attempt * 1.2)
        return []

    def crawl(self, params: QueryParams, count: int = 100) -> list[DiscoveryHit]:
        niche = (params.niche or "").strip()
        hits: list[DiscoveryHit] = []
        seen: set[str] = set()
        budget = max(count, 50)
        resume_state = _load_resume_state() if self.persist_resume else {}

        with httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": "WarmrCommunityScanner/0.2 (+commoncrawl; research)"},
            follow_redirects=True,
        ) as client:
            try:
                cdx_api = self._resolve_cdx_api(client)
            except Exception as exc:  # noqa: BLE001
                print(f"commoncrawl index resolve failed: {exc}", flush=True)
                return []

            index_id = self._index_id or "unknown"
            for pattern in self.patterns:
                if len(hits) >= budget:
                    break
                state_key = f"{index_id}::{pattern}"
                start_page = 0
                if self.persist_resume:
                    raw = resume_state.get(state_key)
                    if isinstance(raw, int):
                        start_page = raw
                    elif isinstance(raw, str) and raw.isdigit():
                        start_page = int(raw)
                pages = self.max_pages_per_pattern or 1
                for page_i in range(pages):
                    if len(hits) >= budget:
                        break
                    page = start_page + page_i
                    if self.delay_ms and (page_i > 0 or pattern != self.patterns[0]):
                        time.sleep(self.delay_ms / 1000.0)
                    rows = self._fetch_page(client, cdx_api, pattern, page=page)
                    if not rows:
                        if self.persist_resume:
                            resume_state[state_key] = 0  # wrap for next cycle on this index
                        break
                    kept = 0
                    for row in rows:
                        url = row.get("url") or ""
                        clean = _canonical_community_url(url)
                        if not clean:
                            continue
                        key = clean.lower().rstrip("/")
                        if key in seen:
                            continue
                        score = community_likelihood(clean)
                        if score < self.min_likelihood:
                            continue
                        if niche and niche.lower() not in {"harvest", "all", "any", "business"}:
                            token = niche.replace("-", " ").split()[0].lower()
                            if token and token not in clean.lower() and len(token) > 3:
                                if score < 0.85:
                                    continue
                        seen.add(key)
                        hits.append(
                            DiscoveryHit(
                                url=clean,
                                title=None,
                                snippet=f"cc_pattern={pattern} likelihood={score}",
                                provider=self.name,
                                query=pattern,
                            )
                        )
                        kept += 1
                        if len(hits) >= budget:
                            break
                    next_page = page + 1
                    if self.persist_resume:
                        resume_state[state_key] = next_page
                    print(
                        f"commoncrawl pattern={pattern!r} page={page} "
                        f"rows={len(rows)} kept={kept} total={len(hits)} next={next_page}",
                        flush=True,
                    )
                    if len(rows) < self.page_size:
                        break

        if self.persist_resume:
            _save_resume_state(resume_state)
        print(f"commoncrawl done hits={len(hits)} budget={budget}", flush=True)
        return hits

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        # Treat query as an optional CDX url pattern override.
        pattern = query.strip() if query.startswith(("*", "http", "www.", "join.")) else None
        if pattern:
            prev = self.patterns
            self.patterns = (pattern,)
            try:
                return self.crawl(QueryParams(niche="harvest"), count=count)
            finally:
                self.patterns = prev
        return self.crawl(QueryParams(niche=query or "harvest"), count=count)
