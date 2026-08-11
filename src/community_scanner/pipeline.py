from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from community_scanner.classify import classify
from community_scanner.config import Settings
from community_scanner.discovery import QueryParams, run_discovery
from community_scanner.discovery.base import resolve_geo
from community_scanner.extract import heuristic_extract, llm_extract_from_text, merge_llm_result
from community_scanner.models import (
    AccessStatus,
    DiscoveryHit,
    ExtractedCommunity,
    NormalizedUrl,
    PipelineRunRow,
    Platform,
    ValueTier,
)
from community_scanner.normalize import JUNK_HINTS, normalize_url
from community_scanner.queue import enqueue_fetch_jobs, fetch_job_from_candidate
from community_scanner.store import save_discovery_hits, upsert_community

USER_AGENT = "WarmrCommunityScanner/0.1 (+https://github.com/warmr-dev/warmr_comunity_scaner)"
log = logging.getLogger(__name__)


def _validate_join_url(join_url: str, *, timeout_seconds: float = 8.0) -> tuple[bool, str, dict]:
    """Best-effort validation for community invite links.

    We run a lightweight GET and look for known "invalid invite" phrases.
    """
    try:
        parsed = urlparse(join_url)
        host = (parsed.netloc or "").lower()
        headers = {"User-Agent": USER_AGENT}

        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
            verify=False,
        ) as client:
            resp = client.get(join_url)
            status_code = resp.status_code
            text_lc = (resp.text or "").lower()

        if "slack.com" in host:
            invalid_phrases = [
                "invite invalid",
                "this invite may be expired",
                "might not have permission to join",
                "does not appear to be a valid invite",
            ]
            if status_code >= 400:
                return False, "slack_http_error", {"status_code": status_code}
            if any(p in text_lc for p in invalid_phrases):
                return (
                    False,
                    "slack_invite_invalid_phrase",
                    {"status_code": status_code},
                )
            return True, "ok", {"status_code": status_code}

        if "wa.me" in host or "whatsapp.com" in host:
            if status_code >= 400:
                return False, "whatsapp_http_error", {"status_code": status_code}
            invalid_phrases = ["404", "not found", "phone number"]
            if any(p in text_lc for p in invalid_phrases):
                return False, "whatsapp_invalid_phrase", {"status_code": status_code}
            return True, "ok", {"status_code": status_code}

        return False, "unsupported_join_platform", {"host": host}
    except Exception as exc:  # noqa: BLE001
        return False, "join_url_validation_exception", {"error": str(exc)[:200]}


def _start_run(session: Session) -> str:
    """Create pipeline_runs row and detach it so mid-run truncates cannot poison flush."""
    run = PipelineRunRow(status="running", metrics={})
    session.add(run)
    session.commit()
    run_id = str(run.id)
    session.expunge(run)
    return run_id


def _finalize_run(
    session: Session,
    run_id: str,
    *,
    status: str,
    metrics: PipelineMetrics,
    error: str | None = None,
) -> str:
    """Commit work + run status; survive deleted pipeline_runs rows."""
    finished = datetime.now(timezone.utc)
    metrics_dict = metrics.as_dict()

    if status == "success":
        try:
            session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("Commit of pipeline work failed: %s", exc)
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
    else:
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass

    try:
        run = session.get(PipelineRunRow, run_id)
        if run is None:
            run = PipelineRunRow(
                id=run_id,
                status=status,
                finished_at=finished,
                metrics=metrics_dict,
                error=error,
            )
            session.add(run)
        else:
            run.status = status
            run.finished_at = finished
            run.metrics = metrics_dict
            run.error = error
        session.commit()
        return run_id
    except Exception as finalize_exc:  # noqa: BLE001
        log.warning("Could not finalize pipeline_runs row %s: %s", run_id, finalize_exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            session.add(
                PipelineRunRow(
                    status=status,
                    finished_at=finished,
                    metrics=metrics_dict,
                    error=error,
                )
            )
            session.commit()
        except Exception:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return run_id


@dataclass
class PipelineMetrics:
    queries_estimated: int = 0
    discovery_hits: int = 0
    normalized: int = 0
    blocked: int = 0
    quality_rejected: int = 0
    fetched: int = 0
    fetch_errors: int = 0
    upserted_new: int = 0
    upserted_changed: int = 0
    upserted_unchanged: int = 0
    skipped_junk: int = 0
    llm_calls: int = 0
    enqueued: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PipelineResult:
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    run_id: str | None = None


@dataclass
class ProcessOutcome:
    item: ExtractedCommunity
    fetched: bool
    llm_calls: int = 0


def _http_limits(concurrency: int) -> httpx.Limits:
    return httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )


def _stub_from_error(hit: DiscoveryHit, norm: NormalizedUrl, exc: Exception, *, scan_geo: str) -> ExtractedCommunity:
    return ExtractedCommunity(
        website=norm.website,
        canonical_key=norm.canonical_key,
        canonical_domain=norm.canonical_domain,
        platform=norm.platform,
        platform_id=norm.platform_id,
        name=hit.title,
        geo=scan_geo,
        access_status=AccessStatus.WATCH,
        value_tier=ValueTier.LOW,
        source_queries=[hit.query] if hit.query else [],
        raw_signals={"fetch_error": str(exc)},
        needs_llm=True,
    )


def _extract_and_classify(
    html: str,
    hit: DiscoveryHit,
    norm: NormalizedUrl,
    settings: Settings,
    *,
    llm_on: bool,
    scan_geo: str,
) -> ProcessOutcome:
    item = heuristic_extract(html, norm, query=hit.query)
    llm_calls = 0
    if llm_on and item.needs_llm:
        llm = llm_extract_from_text(
            html,
            api_key=settings.openai_api_key,
            model=settings.llm_model,
        )
        if llm:
            item = merge_llm_result(item, llm)
            llm_calls = 1
    item = classify(item)
    item = item.model_copy(update={"geo": scan_geo})
    return ProcessOutcome(item=item, fetched=True, llm_calls=llm_calls)


async def _process_candidate_async(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    hit: DiscoveryHit,
    norm: NormalizedUrl,
    settings: Settings,
    *,
    llm_on: bool,
    scan_geo: str,
) -> ProcessOutcome:
    async with semaphore:
        if settings.crawl_download_delay_seconds > 0:
            await asyncio.sleep(settings.crawl_download_delay_seconds)
        try:
            resp = await client.get(norm.website)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            return ProcessOutcome(item=_stub_from_error(hit, norm, exc, scan_geo=scan_geo), fetched=False)

    return _extract_and_classify(html, hit, norm, settings, llm_on=llm_on, scan_geo=scan_geo)


async def _process_candidates_async(
    candidates: list[tuple[DiscoveryHit, NormalizedUrl]],
    settings: Settings,
    *,
    llm_on: bool,
    concurrency: int,
    scan_geo: str,
) -> list[ProcessOutcome]:
    semaphore = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    headers = {"User-Agent": USER_AGENT}

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
        limits=_http_limits(concurrency),
    ) as client:
        tasks = [
            _process_candidate_async(
                client, semaphore, hit, norm, settings, llm_on=llm_on, scan_geo=scan_geo
            )
            for hit, norm in candidates
        ]
        return list(await asyncio.gather(*tasks))


def process_candidates_parallel(
    candidates: list[tuple[DiscoveryHit, NormalizedUrl]],
    settings: Settings,
    *,
    llm_on: bool,
    max_items: int | None = None,
    concurrency: int | None = None,
    scan_geo: str | None = None,
) -> list[ProcessOutcome]:
    if not candidates:
        return []

    limit = max_items if max_items is not None else len(candidates)
    workers = concurrency if concurrency is not None else settings.fetch_concurrency
    batch = candidates[:limit]
    geo = scan_geo or settings.pipe_geo
    return asyncio.run(
        _process_candidates_async(
            batch, settings, llm_on=llm_on, concurrency=workers, scan_geo=geo
        )
    )


def job_to_models(job: dict) -> tuple[DiscoveryHit, NormalizedUrl, str]:
    hit = DiscoveryHit(
        url=job["url"],
        title=job.get("title"),
        snippet=job.get("snippet"),
        provider=job.get("provider", "queue"),
        query=job.get("query"),
    )
    norm = NormalizedUrl(
        original_url=job["url"],
        website=job["website"],
        canonical_domain=job["canonical_domain"],
        platform=Platform(job["platform"]),
        platform_id=job.get("platform_id"),
        canonical_key=job["canonical_key"],
    )
    return hit, norm, job.get("geo") or "USA"


def _stub_from_serp(
    hit: DiscoveryHit,
    norm: NormalizedUrl,
    *,
    scan_geo: str,
    niche: str | None = None,
) -> ExtractedCommunity:
    """Persist SERP hit immediately (no fetch) for volume toward 10k rows."""
    hit_url_lc = (hit.url or "").lower()
    join_url_source_rule = None
    if "slack.com/invite" in hit_url_lc or "slack.com/" in hit_url_lc:
        join_url_source_rule = "slack_serp_invite_url"
    if "wa.me/" in hit_url_lc or "whatsapp.com/" in hit_url_lc:
        join_url_source_rule = "whatsapp_serp_invite_url"

    is_invite = join_url_source_rule is not None

    junk = bool(
        JUNK_HINTS.search(" ".join(filter(None, [hit.url, hit.title or "", hit.snippet or ""])))
    )

    access = AccessStatus.JOIN if is_invite and not junk else AccessStatus.WATCH
    join_url = hit.url if is_invite and not junk else None
    return ExtractedCommunity(
        website=norm.website,
        canonical_key=norm.canonical_key,
        canonical_domain=norm.canonical_domain,
        platform=norm.platform,
        platform_id=norm.platform_id,
        name=hit.title or norm.canonical_domain,
        niche=niche,
        geo=scan_geo,
        join_url=join_url,
        access_status=access,
        value_tier=ValueTier.JUNK if junk else ValueTier.LOW,
        value_score=0 if junk else 15,
        source_queries=[hit.query] if hit.query else [],
        raw_signals={
            "serp_stub": True,
            "snippet": hit.snippet,
            "provider": hit.provider,
            **(
                {
                    "join_url_source": {
                        "rule": join_url_source_rule,
                        "hit_url": hit.url,
                    }
                }
                if join_url_source_rule
                else {}
            ),
        },
        needs_llm=False,
    )


def apply_serp_stubs(
    session: Session,
    candidates: list[tuple[DiscoveryHit, NormalizedUrl]],
    metrics: PipelineMetrics,
    *,
    scan_geo: str,
    niche: str | None = None,
) -> None:
    for hit, norm in candidates:
        item = _stub_from_serp(hit, norm, scan_geo=scan_geo, niche=niche)

        # Validate invite links before writing to Supabase.
        if item.join_url and item.access_status != AccessStatus.REJECT:
            ok, reason, details = _validate_join_url(item.join_url)
            item.raw_signals = {
                **item.raw_signals,
                "join_url_validation": {
                    "ok": ok,
                    "reason": reason,
                    "details": details,
                },
            }
            if not ok:
                item.access_status = AccessStatus.REJECT
                item.value_tier = ValueTier.JUNK
                item.value_score = 0
        if (
            item.access_status == AccessStatus.REJECT
            or item.value_tier == ValueTier.JUNK
            or not item.join_url
        ):
            metrics.skipped_junk += 1
            continue

        _, created, changed = upsert_community(session, item)
        if created:
            metrics.upserted_new += 1
        elif changed:
            metrics.upserted_changed += 1
        else:
            metrics.upserted_unchanged += 1


def apply_outcomes(session: Session, outcomes: list[ProcessOutcome], metrics: PipelineMetrics) -> None:
    for outcome in outcomes:
        if outcome.fetched:
            metrics.fetched += 1
        else:
            metrics.fetch_errors += 1
        metrics.llm_calls += outcome.llm_calls

        # Validate invite links before writing to Supabase.
        if outcome.item.join_url and outcome.item.access_status != AccessStatus.REJECT:
            ok, reason, details = _validate_join_url(outcome.item.join_url)
            outcome.item.raw_signals = {
                **outcome.item.raw_signals,
                "join_url_validation": {
                    "ok": ok,
                    "reason": reason,
                    "details": details,
                },
            }
            if not ok:
                outcome.item.access_status = AccessStatus.REJECT
                outcome.item.value_tier = ValueTier.JUNK
                outcome.item.value_score = 0

        if (
            outcome.item.access_status == AccessStatus.REJECT
            or outcome.item.value_tier == ValueTier.JUNK
            or not outcome.item.join_url
        ):
            metrics.skipped_junk += 1
            continue

        _, created, changed = upsert_community(session, outcome.item)
        if created:
            metrics.upserted_new += 1
        elif changed:
            metrics.upserted_changed += 1
        else:
            metrics.upserted_unchanged += 1


def discover_candidates(
    settings: Settings,
    params: QueryParams,
    *,
    per_query: int,
    query_limit: int,
) -> tuple[list, dict[str, str], list[tuple[DiscoveryHit, NormalizedUrl]], PipelineMetrics]:
    metrics = PipelineMetrics(queries_estimated=query_limit)
    hits = run_discovery(settings, params, per_query=per_query, query_limit=query_limit)
    metrics.discovery_hits = len(hits)

    key_by_url: dict[str, str] = {}
    candidates: list[tuple[DiscoveryHit, NormalizedUrl]] = []
    for hit in hits:
        if not hit.url or hit.url.startswith(("javascript:", "mailto:", "tel:")):
            continue
        norm = normalize_url(hit.url)
        if norm.is_blocked:
            metrics.blocked += 1
            continue
        metrics.normalized += 1
        key_by_url[hit.url] = norm.canonical_key
        candidates.append((hit, norm))

    unique: dict[str, tuple[DiscoveryHit, NormalizedUrl]] = {}
    for hit, norm in candidates:
        unique.setdefault(norm.canonical_key, (hit, norm))

    return hits, key_by_url, list(unique.values()), metrics


def run_discovery_only(
    session: Session,
    settings: Settings,
    params: QueryParams,
    *,
    query_limit: int = 10,
    per_query: int = 5,
    enqueue_all: bool = True,
) -> PipelineResult:
    metrics = PipelineMetrics(queries_estimated=query_limit)
    run_id = _start_run(session)

    try:
        hits, key_by_url, unique_candidates, metrics = discover_candidates(
            settings,
            params,
            per_query=per_query,
            query_limit=query_limit,
        )
        save_discovery_hits(session, hits, key_by_url)

        if enqueue_all and settings.use_fetch_queue and unique_candidates:
            scan_geo = resolve_geo(params.geo)
            jobs = [
                fetch_job_from_candidate(hit, norm, geo=scan_geo)
                for hit, norm in unique_candidates
            ]
            metrics.enqueued = enqueue_fetch_jobs(settings, jobs)

        _finalize_run(session, run_id, status="success", metrics=metrics)
        return PipelineResult(metrics=metrics, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        _finalize_run(session, run_id, status="error", metrics=metrics, error=str(exc))
        raise


def run_fetch_worker(
    session: Session,
    settings: Settings,
    *,
    max_items: int | None = None,
    use_llm: bool | None = None,
) -> PipelineResult:
    from community_scanner.queue import dequeue_fetch_jobs

    metrics = PipelineMetrics()
    run_id = _start_run(session)

    llm_on = settings.llm_enabled if use_llm is None else use_llm
    budget = max_items if max_items is not None else settings.worker_max_items
    processed = 0

    try:
        while processed < budget:
            batch_size = min(settings.fetch_batch_size, budget - processed)
            jobs = dequeue_fetch_jobs(settings, batch_size)
            if not jobs:
                break

            candidates = [job_to_models(job) for job in jobs]
            parallel_candidates = [(hit, norm) for hit, norm, _ in candidates]
            scan_geo = candidates[0][2] if candidates else settings.pipe_geo
            outcomes = process_candidates_parallel(
                parallel_candidates,
                settings,
                llm_on=llm_on,
                max_items=len(parallel_candidates),
                scan_geo=scan_geo,
            )
            apply_outcomes(session, outcomes, metrics)
            session.commit()
            processed += len(candidates)

        _finalize_run(session, run_id, status="success", metrics=metrics)
        return PipelineResult(metrics=metrics, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        _finalize_run(session, run_id, status="error", metrics=metrics, error=str(exc))
        raise


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
    run_id = _start_run(session)

    try:
        hits, key_by_url, unique_candidates, metrics = discover_candidates(
            settings,
            params,
            per_query=per_query,
            query_limit=query_limit,
        )
        save_discovery_hits(session, hits, key_by_url)

        llm_on = settings.llm_enabled if use_llm is None else use_llm
        scan_geo = resolve_geo(params.geo)

        # Volume: write every unique SERP hit immediately, then enrich via fetch.
        apply_serp_stubs(
            session,
            unique_candidates[:max_fetch],
            metrics,
            scan_geo=scan_geo,
            niche=params.niche,
        )
        session.commit()

        inline = unique_candidates[:max_fetch]
        overflow = unique_candidates[max_fetch:]

        outcomes = process_candidates_parallel(
            inline,
            settings,
            llm_on=llm_on,
            max_items=max_fetch,
            scan_geo=scan_geo,
        )
        apply_outcomes(session, outcomes, metrics)

        if overflow and settings.use_fetch_queue:
            jobs = [
                fetch_job_from_candidate(hit, norm, geo=scan_geo)
                for hit, norm in overflow
            ]
            metrics.enqueued = enqueue_fetch_jobs(settings, jobs)

        _finalize_run(session, run_id, status="success", metrics=metrics)
        return PipelineResult(metrics=metrics, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        _finalize_run(session, run_id, status="error", metrics=metrics, error=str(exc))
        raise
