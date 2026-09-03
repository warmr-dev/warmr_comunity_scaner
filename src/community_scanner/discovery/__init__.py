from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from community_scanner.config import Settings
from community_scanner.discovery.base import DiscoveryProvider, QueryParams, generate_queries
from community_scanner.discovery.bing import BingHtmlProvider
from community_scanner.discovery.brave import BraveSearchProvider
from community_scanner.discovery.ddg import DuckDuckGoProvider
from community_scanner.discovery.directory_crawler import DirectoryCrawlerProvider
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
                    country=settings.brave_country,
                    search_lang=settings.brave_search_lang,
                    max_requests=settings.brave_max_requests,
                )
            )
        elif name in {"ddg", "duckduckgo"}:
            providers.append(
                DuckDuckGoProvider(
                    timeout=settings.http_timeout_seconds,
                    delay=max(1.2, settings.crawl_download_delay_seconds or 1.5),
                )
            )
        elif name == "bing":
            providers.append(
                BingHtmlProvider(
                    timeout=settings.http_timeout_seconds,
                    delay=max(1.0, settings.crawl_download_delay_seconds or 1.2),
                )
            )
        elif name in ("directory", "directories"):
            providers.append(
                DirectoryCrawlerProvider(
                    timeout=settings.http_timeout_seconds,
                    delay=max(0.2, settings.crawl_download_delay_seconds or 0.4),
                    max_channels_per_site=settings.directory_max_channels_per_site,
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
    except Exception as exc:  # noqa: BLE001
        print(f"discovery error [{provider.name}] {exc!s}"[:240], flush=True)
        return []


def _crawl_safe(provider: DiscoveryProvider, params: QueryParams, count: int) -> list[DiscoveryHit]:
    crawl = getattr(provider, "crawl", None)
    if not callable(crawl):
        return []
    try:
        return crawl(params, count=count)
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
            "No discovery providers configured. "
            "Set DISCOVERY_PROVIDERS=ddg,searxng,directory, or brave."
        )

    hits: list[DiscoveryHit] = []
    seen_urls: set[str] = set()
    budget = per_query * query_limit

    crawl_providers = [p for p in providers if callable(getattr(p, "crawl", None))]
    search_providers = [p for p in providers if p not in crawl_providers]

    delay = max(0.0, settings.crawl_download_delay_seconds)
    if "searxng" in settings.discovery_provider_list and delay <= 0:
        delay = 0.6

    for provider in crawl_providers:
        print(f"directory crawl start [{provider.name}] budget={budget}", flush=True)
        crawled = 0
        for hit in _crawl_safe(provider, params, budget):
            crawled += 1
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            hits.append(hit)
        print(
            f"directory crawl done [{provider.name}] raw={crawled} unique_total={len(hits)}",
            flush=True,
        )

    if not search_providers:
        return hits

    harvest = bool(settings.harvest_mode)
    queries = generate_queries(params, limit=query_limit, harvest=harvest)
    tasks: list[tuple[DiscoveryProvider, str]] = [
        (provider, query) for query in queries for provider in search_providers
    ]
    if not tasks:
        return hits

    workers = min(settings.discovery_concurrency, len(tasks))
    total = len(tasks)
    print(
        f"discovery start providers={[p.name for p in search_providers]} "
        f"harvest={harvest} queries={len(queries)} tasks={total} concurrency={workers}",
        flush=True,
    )

    # Sequential when concurrency=1 (recommended): one query at a time with pause.
    if workers <= 1:
        for i, (provider, query) in enumerate(tasks, start=1):
            batch = _search_safe(provider, query, per_query)
            for hit in batch:
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                hits.append(hit)
            if i == 1 or i == total or i % 5 == 0:
                print(
                    f"discovery {i}/{total} [{provider.name}] hits=+{len(batch)} total={len(hits)} "
                    f"q={query[:80]!r}",
                    flush=True,
                )
            if delay > 0:
                time.sleep(delay)
        print(f"discovery done hits={len(hits)}", flush=True)
        return hits

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for provider, query in tasks:
            futures[executor.submit(_search_safe, provider, query, per_query)] = (provider, query)
            if delay > 0:
                time.sleep(delay / max(workers, 1))
        for future in as_completed(futures):
            provider, query = futures[future]
            batch = future.result()
            for hit in batch:
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                hits.append(hit)
            done += 1
            if done == 1 or done == total or done % 5 == 0:
                print(
                    f"discovery {done}/{total} [{provider.name}] hits=+{len(batch)} "
                    f"total={len(hits)} q={query[:80]!r}",
                    flush=True,
                )

    print(f"discovery done hits={len(hits)}", flush=True)
    return hits


__all__ = [
    "QueryParams",
    "build_providers",
    "generate_queries",
    "run_discovery",
]
