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
            providers.append(
                SearxngProvider(
                    base_url=settings.searxng_base_url,
                    timeout=settings.http_timeout_seconds,
                )
            )
    return providers


def run_discovery(
    settings: Settings,
    params: QueryParams,
    per_query: int = 10,
    query_limit: int = 20,
) -> list[DiscoveryHit]:
    providers = build_providers(settings)
    queries = generate_queries(params, limit=query_limit)
    hits: list[DiscoveryHit] = []
    seen_urls: set[str] = set()

    for query in queries:
        for provider in providers:
            try:
                batch = provider.search(query, count=per_query)
            except Exception:
                continue
            for hit in batch:
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
