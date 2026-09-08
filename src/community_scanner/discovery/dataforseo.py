"""DataForSEO SERP discovery provider (cheap fresh layer)."""

from __future__ import annotations

import base64
import time

import httpx

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.models import DiscoveryHit

_TASK_POST = "https://api.dataforseo.com/v3/serp/google/organic/task_post"
_TASK_GET = "https://api.dataforseo.com/v3/serp/google/organic/task_get/regular/{id}"
_LIVE = "https://api.dataforseo.com/v3/serp/google/organic/live/regular"


class DataForSeoProvider(DiscoveryProvider):
    name = "dataforseo"

    def __init__(
        self,
        *,
        login: str,
        password: str,
        timeout: float = 60.0,
        mode: str = "live",
        location_code: int = 2840,  # United States
        language_code: str = "en",
        depth: int = 10,
    ) -> None:
        self.login = login
        self.password = password
        self.timeout = timeout
        self.mode = (mode or "live").strip().lower()
        self.location_code = location_code
        self.language_code = language_code
        self.depth = max(10, min(depth, 100))

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        return f"Basic {token}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }

    def _payload(self, query: str, count: int) -> list[dict]:
        return [
            {
                "keyword": query,
                "location_code": self.location_code,
                "language_code": self.language_code,
                "depth": max(count, self.depth),
                "se_domain": "google.com",
            }
        ]

    def _parse_items(self, data: dict, query: str, count: int) -> list[DiscoveryHit]:
        hits: list[DiscoveryHit] = []
        tasks = data.get("tasks") or []
        for task in tasks:
            result_list = task.get("result") or []
            for result in result_list:
                items = result.get("items") or []
                for item in items:
                    if item.get("type") and item.get("type") != "organic":
                        continue
                    url = item.get("url")
                    if not url:
                        continue
                    hits.append(
                        DiscoveryHit(
                            url=url,
                            title=item.get("title"),
                            snippet=item.get("description"),
                            provider=self.name,
                            query=query,
                        )
                    )
                    if len(hits) >= count:
                        return hits
        return hits

    def _search_live(self, query: str, count: int) -> list[DiscoveryHit]:
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                _LIVE,
                headers=self._headers(),
                json=self._payload(query, count),
            )
            resp.raise_for_status()
            return self._parse_items(resp.json(), query, count)

    def _search_standard(self, query: str, count: int) -> list[DiscoveryHit]:
        with httpx.Client(timeout=self.timeout) as client:
            post = client.post(
                _TASK_POST,
                headers=self._headers(),
                json=self._payload(query, count),
            )
            post.raise_for_status()
            body = post.json()
            tasks = body.get("tasks") or []
            if not tasks:
                return []
            task_id = tasks[0].get("id")
            if not task_id:
                return []

            # Poll a few times; standard queue is usually ready within minutes,
            # but for CLI smoke we keep this short and return whatever is ready.
            for attempt in range(1, 8):
                time.sleep(min(2.0 * attempt, 8.0))
                get = client.get(
                    _TASK_GET.format(id=task_id),
                    headers=self._headers(),
                )
                if get.status_code == 404:
                    continue
                get.raise_for_status()
                data = get.json()
                status = ((data.get("tasks") or [{}])[0]).get("status_code")
                # 20000 = Ok
                if status == 20000:
                    return self._parse_items(data, query, count)
            print(f"dataforseo task not ready id={task_id}", flush=True)
            return []

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        if not self.login or not self.password:
            return []
        try:
            if self.mode in {"standard", "priority"}:
                return self._search_standard(query, count)
            return self._search_live(query, count)
        except Exception as exc:  # noqa: BLE001
            print(f"dataforseo error: {exc!s}"[:240], flush=True)
            return []
