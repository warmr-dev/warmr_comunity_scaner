from __future__ import annotations

import os
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.I | re.S,
)
_SNIPPET_RE = re.compile(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or "")).strip()


def _unwrap_ddg_url(href: str) -> str | None:
    href = unescape((href or "").strip())
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    if "uddg" in qs and qs["uddg"]:
        return unquote(qs["uddg"][0])
    if parsed.scheme in {"http", "https"} and "duckduckgo.com" not in (parsed.netloc or "").lower():
        return href
    return None


class DuckDuckGoProvider(DiscoveryProvider):
    """HTML DuckDuckGo search — free local discovery without SearXNG/Docker."""

    name = "ddg"
    _lock_path = Path(__file__).resolve().parents[3] / "data" / "ddg_rate.lock"

    def __init__(self, timeout: float = 20.0, delay: float = 1.5) -> None:
        self.timeout = timeout
        self.delay = delay
        self._last_request = 0.0

    def _global_throttle(self) -> None:
        """Cross-process spacing so parallel workers do not trip DDG 403."""
        path = self._lock_path
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
                time.sleep(self.delay)
                return
            except FileExistsError:
                try:
                    age = time.time() - path.stat().st_mtime
                    if age > max(self.delay * 3, 5.0):
                        path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                time.sleep(0.2)
        time.sleep(self.delay)

    def _release_throttle(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        self._global_throttle()
        hits: list[DiscoveryHit] = []
        seen: set[str] = set()
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                resp = client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": ""},
                )
                self._last_request = time.monotonic()
                if resp.status_code == 403:
                    time.sleep(self.delay * 2)
                    resp = client.post(
                        "https://html.duckduckgo.com/html/",
                        data={"q": query, "b": ""},
                    )
                resp.raise_for_status()
                html = resp.text or ""
        finally:
            self._release_throttle()

        snippets = [_strip_html(m.group(1)) for m in _SNIPPET_RE.finditer(html)]
        for idx, match in enumerate(_RESULT_RE.finditer(html)):
            url = _unwrap_ddg_url(match.group(1))
            if not url:
                continue
            key = url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            title = _strip_html(match.group(2)) or None
            snippet = snippets[idx] if idx < len(snippets) else None
            hits.append(
                DiscoveryHit(
                    url=url,
                    title=title,
                    snippet=snippet,
                    provider=self.name,
                    query=query,
                )
            )
            if len(hits) >= count:
                break
        return hits
