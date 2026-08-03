from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from sqlalchemy.orm import Session

from community_scanner.classify import classify
from community_scanner.config import Settings
from community_scanner.discovery import QueryParams, run_discovery
from community_scanner.extract import heuristic_extract, llm_extract_from_text, merge_llm_result
from community_scanner.models import PipelineRunRow
from community_scanner.normalize import normalize_url
from community_scanner.store import save_discovery_hits, upsert_community


@dataclass
class PipelineMetrics:
    queries_estimated: int = 0
    discovery_hits: int = 0
    normalized: int = 0
    blocked: int = 0
    fetched: int = 0
    fetch_errors: int = 0
    upserted_new: int = 0
    upserted_changed: int = 0
    upserted_unchanged: int = 0
    llm_calls: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PipelineResult:
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    run_id: str | None = None


def fetch_html(url: str, timeout: float) -> str:
    headers = {
        "User-Agent": "WarmrCommunityScanner/0.1 (+https://github.com/warmr-dev/warmr_comunity_scaner)"
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def run_pipeline(
    session: Session,
    settings: Settings,
    params: QueryParams,
    *,
    query_limit: int = 10,
    per_query: int = 5,
    max_fetch: int = 30,
    use_llm: bool | None = None,
) -> PipelineResult:
    metrics = PipelineMetrics(queries_estimated=query_limit)
    run = PipelineRunRow(status="running", metrics={})
    session.add(run)
    session.commit()

    try:
        hits = run_discovery(settings, params, per_query=per_query, query_limit=query_limit)
        metrics.discovery_hits = len(hits)

        key_by_url: dict[str, str] = {}
        candidates = []
        for hit in hits:
            norm = normalize_url(hit.url)
            if norm.is_blocked:
                metrics.blocked += 1
                continue
            metrics.normalized += 1
            key_by_url[hit.url] = norm.canonical_key
            candidates.append((hit, norm))

        save_discovery_hits(session, hits, key_by_url)

        # Deduplicate by canonical_key before fetch
        unique: dict[str, tuple] = {}
        for hit, norm in candidates:
            unique.setdefault(norm.canonical_key, (hit, norm))

        llm_on = settings.llm_enabled if use_llm is None else use_llm

        for hit, norm in list(unique.values())[:max_fetch]:
            try:
                html = fetch_html(norm.website, settings.http_timeout_seconds)
                metrics.fetched += 1
            except Exception as exc:  # noqa: BLE001
                metrics.fetch_errors += 1
                # Still store a stub watch row from discovery metadata
                from community_scanner.models import AccessStatus, ExtractedCommunity, ValueTier

                stub = ExtractedCommunity(
                    website=norm.website,
                    canonical_key=norm.canonical_key,
                    canonical_domain=norm.canonical_domain,
                    platform=norm.platform,
                    platform_id=norm.platform_id,
                    name=hit.title,
                    access_status=AccessStatus.WATCH,
                    value_tier=ValueTier.LOW,
                    source_queries=[hit.query] if hit.query else [],
                    raw_signals={"fetch_error": str(exc)},
                    needs_llm=True,
                )
                _, created, changed = upsert_community(session, stub)
                if created:
                    metrics.upserted_new += 1
                elif changed:
                    metrics.upserted_changed += 1
                else:
                    metrics.upserted_unchanged += 1
                continue

            item = heuristic_extract(html, norm, query=hit.query)
            if llm_on and item.needs_llm:
                llm = llm_extract_from_text(
                    html,
                    api_key=settings.openai_api_key,
                    model=settings.llm_model,
                )
                if llm:
                    item = merge_llm_result(item, llm)
                    metrics.llm_calls += 1

            item = classify(item)
            _, created, changed = upsert_community(session, item)
            if created:
                metrics.upserted_new += 1
            elif changed:
                metrics.upserted_changed += 1
            else:
                metrics.upserted_unchanged += 1

        from datetime import datetime, timezone

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.metrics = metrics.as_dict()
        session.commit()
        return PipelineResult(metrics=metrics, run_id=run.id)
    except Exception as exc:  # noqa: BLE001
        from datetime import datetime, timezone

        run.status = "error"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        run.metrics = metrics.as_dict()
        session.commit()
        raise
