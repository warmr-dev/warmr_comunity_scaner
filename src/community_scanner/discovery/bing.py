"""Bing HTML search provider — free fallback when DDG HTML is rate-limited."""

from __future__ import annotations

import base64
import os
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<h2[^>]*>\s*<a[^>]*>(.*?)</a>", re.I | re.S)
_SNIPPET_RE = re.compile(r"<p[^>]*class=\"b_lineclamp\d+\"[^>]*>(.*?)</p>", re.I | re.S)


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub(" ", text or "")).strip()


def _decode_bing_ck(href: str) -> str | None:
    href = unescape((href or "").strip())
    if not href.startswith("http"):
        return None
    parsed = urlparse(href)
    host = (parsed.netloc or "").lower()
    if "bing.com" not in host:
        if parsed.scheme in {"http", "https"}:
            return href
        return None
    qs = parse_qs(parsed.query)
    raw = (qs.get("u") or [""])[0]
    if not raw:
        return None
    if raw.startswith("a1"):
        raw = raw[2:]
    pad = "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw + pad).decode("utf-8", "ignore")
    except Exception:
        return None
    if decoded.startswith("http"):
        return decoded
    return None


class BingHtmlProvider(DiscoveryProvider):
    name = "bing"

    _lock_path = Path(__file__).resolve().parents[3] / "data" / "bing_rate.lock"

    def __init__(self, timeout: float = 20.0, delay: float = 1.2) -> None:
        self.timeout = timeout
        self.delay = delay

    def _throttle(self) -> None:
        path = self._lock_path
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                time.sleep(self.delay)
                return
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > max(self.delay * 3, 5.0):
                        try:
                            path.unlink(missing_ok=True)
                        except PermissionError:
                            # Another Windows worker still owns the lock.
                            time.sleep(0.25)
                        continue
                except OSError:
                    pass
                time.sleep(0.15)
        time.sleep(self.delay)

    def _release(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        self._throttle()
        hits: list[DiscoveryHit] = []
        seen: set[str] = set()
        try:
            url = (
                f"https://www.bing.com/search?q={quote_plus(query)}"
                f"&count={min(count, 30)}&setlang=en-us&cc=US"
            )
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text or ""
        finally:
            self._release()

        blocks = re.split(r'<li class="b_algo"', html, flags=re.I)[1:]
        for block in blocks:
            chunk = block[:4000]
            m = re.search(r'href="(https://www\.bing\.com/ck/[^"]+|https?://[^"]+)"', chunk, re.I)
            if not m:
                continue
            href = _decode_bing_ck(m.group(1))
            if not href:
                continue
            host = (urlparse(href).netloc or "").lower()
            if any(x in host for x in ("bing.com", "microsoft.com", "msn.com", "r.bing.com")):
                continue
            key = href.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            title_m = _TITLE_RE.search(chunk)
            snip_m = _SNIPPET_RE.search(chunk)
            hits.append(
                DiscoveryHit(
                    url=href,
                    title=_strip_html(title_m.group(1)) if title_m else None,
                    snippet=_strip_html(snip_m.group(1)) if snip_m else None,
                    provider=self.name,
                    query=query,
                )
            )
            if len(hits) >= count:
                break
        return hits
