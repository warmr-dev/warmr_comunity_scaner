from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from community_scanner.config import Settings
from community_scanner.discovery.base import DiscoveryProvider, QueryParams, generate_queries
from community_scanner.discovery.brave import BraveSearchProvider
from community_scanner.discovery.searxng import SearxngProvider
from community_scanner.discovery.seeds import SeedsProvider
from community_scanner.models import DiscoveryHit


def build_providers(settings: Settings) -> list[DiscoveryProvider]:
    providers: list[DiscoveryProvider] = []
    for name in settings.discovery_provider_list:
        if name == "seeds":
            providers.append(SeedsProvider())
        elif name == "brave":
            providers.append(
                BraveSearchProvider(
                    api_key=settings.brave_search_api_key,
                    timeout=settings.http_timeout_seconds,
                )
            )
        elif name == "searxng":
            if settings.searxng_base_url:
                providers.append(
                    SearxngProvider(
                        base_url=settings.searxng_base_url,
                        timeout=settings.http_timeout_seconds,
                        language=settings.searxng_language,
                    )
                )
    return providers


def _search_safe(provider: DiscoveryProvider, query: str, per_query: int) -> list[DiscoveryHit]:
    try:
        return provider.search(query, count=per_query)
    except Exception:
        return []


def run_discovery(
    settings: Settings,
    params: QueryParams,
    per_query: int = 10,
    query_limit: int = 20,
) -> list[DiscoveryHit]:
    import time

    providers = build_providers(settings)
    if not providers:
        raise RuntimeError(
            "No discovery providers configured. Set DISCOVERY_PROVIDERS=searxng and SEARXNG_BASE_URL."
        )

    queries = generate_queries(params, limit=query_limit)
    hits: list[DiscoveryHit] = []
    seen_urls: set[str] = set()

    tasks: list[tuple[DiscoveryProvider, str]] = [
        (provider, query) for query in queries for provider in providers
    ]

    workers = min(settings.discovery_concurrency, len(tasks))
    # Space out SearXNG queries — cloud IPs get rate-limited quickly.
    delay = max(0.0, settings.crawl_download_delay_seconds)
    if "searxng" in settings.discovery_provider_list and delay < 2.0:
        delay = 2.5

    # Sequential when concurrency=1 (recommended): one query at a time with pause.
    if workers <= 1:
        for provider, query in tasks:
            for hit in _search_safe(provider, query, per_query):
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                hits.append(hit)
            if delay > 0:
                time.sleep(delay)
        return hits

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for provider, query in tasks:
            futures[executor.submit(_search_safe, provider, query, per_query)] = (provider, query)
            if delay > 0:
                time.sleep(delay / max(workers, 1))
        for future in as_completed(futures):
            for hit in future.result():
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                hits.append(hit)

    return hits


__all__ = [
    "QueryParams",
    "build_providers",
    "generate_queries",
    "run_discovery",
]
