from __future__ import annotations

import threading
import time

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Brave free tier: 1 request/second. Paid tier: up to 50 req/s.
_DEFAULT_RETRY_AFTER = 2.0
_MAX_RETRIES = 3


class BraveSearchProvider(DiscoveryProvider):
    name = "brave"
    _requests_used = 0
    _lock = threading.Lock()

    def __init__(
        self,
        api_key: str,
        timeout: float = 20.0,
        country: str = "us",
        search_lang: str = "en",
        extra_snippets: bool = True,
        max_requests: int = 0,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.country = country
        self.search_lang = search_lang
        self.extra_snippets = extra_snippets
        self.max_requests = max_requests
        self._budget_logged = False

    @classmethod
    def requests_used(cls) -> int:
        with cls._lock:
            return cls._requests_used

    def _budget_remaining(self) -> bool:
        if self.max_requests <= 0:
            return True
        with self._lock:
            if self._requests_used >= self.max_requests:
                if not self._budget_logged:
                    print(
                        f"brave budget reached ({self.max_requests} requests), "
                        "skipping further Brave calls",
                        flush=True,
                    )
                    self._budget_logged = True
                return False
            return True

    def _record_request(self) -> None:
        with self._lock:
            type(self)._requests_used += 1

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        if not self.api_key:
            return []
        if not self._budget_remaining():
            return []

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params: dict = {
            "q": query,
            "count": min(count, 20),
            "country": self.country,
            "search_lang": self.search_lang,
            "safesearch": "off",
            "extra_snippets": "true" if self.extra_snippets else "false",
        }

        data: dict = {}
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)

                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", _DEFAULT_RETRY_AFTER))
                    wait = retry_after * attempt
                    print(f"brave 429 — sleeping {wait:.1f}s (attempt {attempt})", flush=True)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                self._record_request()
                break

            except httpx.HTTPStatusError:
                if attempt == _MAX_RETRIES:
                    raise
                time.sleep(_DEFAULT_RETRY_AFTER * attempt)
            except httpx.RequestError:
                if attempt == _MAX_RETRIES:
                    raise
                time.sleep(_DEFAULT_RETRY_AFTER * attempt)

        hits: list[DiscoveryHit] = []
        for item in data.get("web", {}).get("results", [])[:count]:
            url = item.get("url")
            if not url:
                continue

            # Combine main description with extra_snippets for richer snippet text.
            description = item.get("description") or ""
            extras: list[str] = item.get("extra_snippets") or []
            snippet = description
            if extras:
                snippet = description + " | " + " | ".join(extras[:2])

            hits.append(
                DiscoveryHit(
                    url=url,
                    title=item.get("title"),
                    snippet=snippet.strip(" |") or None,
                    provider=self.name,
                    query=query,
                )
            )
        return hits
