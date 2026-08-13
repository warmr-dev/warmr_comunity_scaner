from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session
from community_scanner.classify import classify
from community_scanner.config import Settings
from community_scanner.content_filter import is_adult_community
from community_scanner.language_filter import is_russian_community
from community_scanner.discovery import QueryParams, run_discovery
from community_scanner.discovery.base import resolve_geo
from community_scanner.extract import heuristic_extract, llm_extract_from_text, merge_llm_result
from community_scanner.invites import (
    MIN_MEMBERS_FOR_UPSERT,
    SIZE_OPTIONAL_PLATFORMS,
    classify_invite_url,
    enrich_invite_page,
    find_all_invites_in_text,
    find_invite_in_text,
    invite_from_platform_page,
    parse_member_count,
)
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
    """Accept invite-shaped URLs; only reject on explicit expired/invalid phrases.

    Slack/Discord/WhatsApp often return 403/challenge pages to datacenter IPs — that
    must NOT discard a correctly shaped invite.
    """
    match = classify_invite_url(join_url)
    if not match:
        return False, "not_invite_shape", {"url": join_url[:200]}

    details: dict = {
        "platform": match.platform,
        "rule": match.rule,
        "canonical_join_url": match.url,
    }
    try:
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
            verify=False,
        ) as client:
            resp = client.get(match.url)
            status_code = resp.status_code
            text_lc = (resp.text or "").lower()
        details["status_code"] = status_code

        invalid_by_platform = {
            "slack": [
                "invite invalid",
                "this invite may be expired",
                "might not have permission to join",
                "does not appear to be a valid invite",
                "workspace not found",
            ],
            "whatsapp": [
                "invite link has been revoked",
                "invite link is invalid",
                "this invite link has expired",
            ],
            "telegram": [
                "sorry, this channel doesn't seem to exist",
                "this invite link is invalid",
                "invite link is invalid or has expired",
            ],
            "discord": [
                "invite invalid",
                "invalid invite",
                "unable to accept invite",
                "this invite may be expired",
            ],
        }
        # Only trust invalid phrases when we actually got a readable success page.
        if 200 <= status_code < 400:
            for phrase in invalid_by_platform.get(match.platform, []):
                if phrase in text_lc:
                    return False, f"{match.platform}_invite_invalid_phrase", details

        return True, "ok", details
    except Exception as exc:  # noqa: BLE001
        details["error"] = str(exc)[:200]
        return True, "ok_shape_only", details


def _invite_from_hit(hit: DiscoveryHit, norm: NormalizedUrl | None = None):
    """Prefer direct hit URL, then invite buried in title/snippet, then platform page."""
    invite = classify_invite_url(hit.url or "")
    if invite:
        return invite, "hit_url"
    blob = " ".join(filter(None, [hit.title or "", hit.snippet or "", hit.url or ""]))
    invite = find_invite_in_text(blob)
    if invite:
        return invite, "serp_snippet"
    if norm is not None:
        invite = invite_from_platform_page(
            norm.website,
            getattr(norm.platform, "value", str(norm.platform)),
            norm.platform_id,
        )
        if invite:
            return invite, "platform_page"
    return None, None


DIRECTORY_HOST_HINTS = (
    "tgstat.",
    "telemetr.",
    "combot.org",
    "tlgrm.ru",
    "t.me",
    "telegram.me",
    "chat.whatsapp.com",
    "whatsapp.com",
    "join.slack.com",
    "slack.com",
    "discord.gg",
    "discord.com",
    "disboard.org",
    "top.gg",
    "discord.me",
)


def _invite_priority(hit: DiscoveryHit, norm: NormalizedUrl) -> int:
    """Higher = fetch first. Prefer invite URLs and directory hosts."""
    score = 0
    url_lc = (hit.url or "").lower()
    blob = " ".join(filter(None, [url_lc, hit.title or "", hit.snippet or ""])).lower()
    if classify_invite_url(hit.url or ""):
        score += 100
    if any(h in url_lc for h in DIRECTORY_HOST_HINTS):
        score += 50
    if any(
        x in blob
        for x in (
            "t.me/",
            "chat.whatsapp.com",
            "join.slack.com",
            "shared_invite",
            "discord.gg",
            "discord.com/invite",
        )
    ):
        score += 30
    if any(x in blob for x in ("telegram", "whatsapp", "slack", "discord")):
        score += 10
    return score


def _item_from_invite(
    invite_url: str,
    *,
    scan_geo: str,
    niche: str | None,
    name: str | None,
    source_queries: list[str],
    raw_signals: dict,
    harvest: bool = False,
) -> ExtractedCommunity | None:
    invite = classify_invite_url(invite_url)
    if not invite:
        return None
    norm = normalize_url(invite.url)
    if norm.is_blocked:
        return None
    if is_adult_community(
        name=name,
        url=invite.url,
        platform_id=norm.platform_id,
        snippet=str(raw_signals.get("snippet") or raw_signals.get("directory_size_text") or ""),
    ):
        return None

    flags: dict = {}
    if is_russian_community(
        name=name,
        url=invite.url,
        platform_id=norm.platform_id,
        snippet=str(raw_signals.get("snippet") or raw_signals.get("directory_size_text") or ""),
        source_url=str(raw_signals.get("from_page") or raw_signals.get("hit_url") or ""),
    ):
        if not harvest:
            return None
        flags["maybe_russian"] = True

    return ExtractedCommunity(
        website=norm.website,
        canonical_key=norm.canonical_key,
        canonical_domain=norm.canonical_domain,
        platform=norm.platform,
        platform_id=norm.platform_id,
        name=name or invite.url,
        niche=niche,
        geo=scan_geo,
        join_url=invite.url,
        access_status=AccessStatus.JOIN,
        value_tier=ValueTier.LOW,
        value_score=30,
        source_queries=source_queries,
        raw_signals={
            **raw_signals,
            **flags,
            "harvest": harvest,
            "join_url_source": {
                "rule": invite.rule,
                "platform": invite.platform,
                "url": invite.url,
            },
        },
        needs_llm=False,
    )


def _upsert_invite_item(
    session: Session,
    item: ExtractedCommunity,
    metrics: PipelineMetrics,
    *,
    harvest: bool = False,
    skip_enrich: bool = False,
) -> None:
    if not item.join_url:
        metrics.note_reject("missing_join_url")
        return
    if is_adult_community(
        name=item.name,
        url=item.join_url,
        platform_id=item.platform_id,
        snippet=str(item.raw_signals),
    ):
        item.raw_signals = {**item.raw_signals, "reject_reason": "adult_content"}
        metrics.note_reject("adult_content")
        return

    russian = is_russian_community(
        name=item.name,
        url=item.join_url,
        platform_id=item.platform_id,
        snippet=str(item.raw_signals),
        source_url=str(item.raw_signals.get("from_page") or item.raw_signals.get("hit_url") or ""),
    )
    if russian and not harvest:
        item.raw_signals = {**item.raw_signals, "reject_reason": "russian_content"}
        metrics.note_reject("russian_content")
        return
    if russian and harvest:
        item.raw_signals = {**item.raw_signals, "maybe_russian": True}

    invite = classify_invite_url(item.join_url)
    if not invite:
        item.raw_signals = {**item.raw_signals, "reject_reason": "not_invite_shape"}
        metrics.note_reject("not_invite_shape")
        return
    item.join_url = invite.url

    if not skip_enrich:
        # Enrich from invite landing page (Telegram shows subscriber count publicly).
        meta = enrich_invite_page(item.join_url)
        item.raw_signals = {
            **item.raw_signals,
            "invite_page": {
                "ok": meta.get("ok"),
                "status_code": meta.get("status_code"),
                "size_members": meta.get("size_members"),
                "size_text": meta.get("size_text"),
                "error": meta.get("error"),
            },
        }
        if meta.get("name") and (
            not item.name
            or item.name.startswith("http")
            or item.name == item.canonical_domain
            or "list" in (item.name or "").lower()
        ):
            item.name = meta["name"]
        if meta.get("size_members") is not None:
            item.size_members = int(meta["size_members"])
            item.size_text = meta.get("size_text") or item.size_text

        if item.size_members is None:
            for blob in (
                item.raw_signals.get("directory_size_text"),
                item.raw_signals.get("snippet"),
            ):
                if not blob:
                    continue
                parsed, parsed_text = parse_member_count(str(blob))
                if parsed is not None:
                    item.size_members = parsed
                    item.size_text = parsed_text or item.size_text
                    break

    if not harvest:
        platform_lc = (invite.platform or "").lower()
        size_optional = platform_lc in SIZE_OPTIONAL_PLATFORMS
        if item.size_members is not None and item.size_members < MIN_MEMBERS_FOR_UPSERT:
            item.raw_signals = {
                **item.raw_signals,
                "reject_reason": "too_small",
                "min_members": MIN_MEMBERS_FOR_UPSERT,
            }
            metrics.note_reject("too_small")
            return
        if item.size_members is None and not size_optional:
            item.raw_signals = {
                **item.raw_signals,
                "reject_reason": "too_small_or_unknown_size",
                "min_members": MIN_MEMBERS_FOR_UPSERT,
            }
            metrics.note_reject("too_small_or_unknown_size")
            return

        ok, reason, details = _validate_join_url(item.join_url)
        item.raw_signals = {
            **item.raw_signals,
            "join_url_validation": {"ok": ok, "reason": reason, "details": details},
        }
        if not ok:
            item.raw_signals = {**item.raw_signals, "reject_reason": f"join_invalid:{reason}"}
            metrics.note_reject(f"join_invalid:{reason}")
            return

        item = classify(item)
        if item.access_status == AccessStatus.REJECT or item.value_tier == ValueTier.JUNK:
            item.raw_signals = {**item.raw_signals, "reject_reason": "classify_junk"}
            metrics.note_reject("classify_junk")
            return
    else:
        # Harvest: keep invite-shaped URLs; tag for later filtering.
        item.raw_signals = {**item.raw_signals, "harvest": True}
        if item.size_members is not None and item.size_members < MIN_MEMBERS_FOR_UPSERT:
            item.raw_signals = {**item.raw_signals, "maybe_too_small": True}
        item = classify(item)
        if item.access_status == AccessStatus.REJECT or item.value_tier == ValueTier.JUNK:
            item.access_status = AccessStatus.WATCH
            item.value_tier = ValueTier.LOW
            item.value_score = max(item.value_score or 0, 20)
            item.raw_signals = {
                **item.raw_signals,
                "harvest_kept": True,
                "classify_would_reject": True,
            }

    _, created, changed = upsert_community(session, item)
    if created:
        metrics.upserted_new += 1
    elif changed:
        metrics.upserted_changed += 1
    else:
        metrics.upserted_unchanged += 1


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
    reject_reasons: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def note_reject(self, reason: str) -> None:
        key = reason or "unknown"
        self.reject_reasons[key] = int(self.reject_reasons.get(key, 0)) + 1
        self.skipped_junk += 1


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
    # If the SERP URL (or snippet) already is an invite, keep it even when HTML has none.
    if not item.join_url:
        invite, source = _invite_from_hit(hit, norm)
        if invite:
            item = item.model_copy(
                update={
                    "join_url": invite.url,
                    "raw_signals": {
                        **item.raw_signals,
                        "join_url_source": {
                            "rule": invite.rule,
                            "platform": invite.platform,
                            "from": source,
                            "hit_url": hit.url,
                        },
                    },
                }
            )
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
        # Prefer the original SERP URL (invite links) over normalized website root.
        fetch_url = hit.url or norm.website
        try:
            resp = await client.get(fetch_url)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:  # noqa: BLE001
            # Still salvage if the URL itself is a valid invite shape.
            invite, source = _invite_from_hit(hit, norm)
            if invite:
                item = ExtractedCommunity(
                    website=norm.website,
                    canonical_key=norm.canonical_key,
                    canonical_domain=norm.canonical_domain,
                    platform=norm.platform,
                    platform_id=norm.platform_id,
                    name=hit.title or norm.canonical_domain,
                    geo=scan_geo,
                    join_url=invite.url,
                    access_status=AccessStatus.JOIN,
                    value_tier=ValueTier.LOW,
                    value_score=20,
                    source_queries=[hit.query] if hit.query else [],
                    raw_signals={
                        "fetch_error": str(exc)[:200],
                        "join_url_source": {
                            "rule": invite.rule,
                            "platform": invite.platform,
                            "from": source,
                            "hit_url": hit.url,
                        },
                    },
                    needs_llm=False,
                )
                return ProcessOutcome(item=classify(item), fetched=False)
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
    print(f"fetch start items={len(batch)} concurrency={workers}", flush=True)
    outcomes = asyncio.run(
        _process_candidates_async(
            batch, settings, llm_on=llm_on, concurrency=workers, scan_geo=geo
        )
    )
    print(
        f"fetch done items={len(outcomes)} "
        f"ok={sum(1 for o in outcomes if o.fetched)} "
        f"err={sum(1 for o in outcomes if not o.fetched)}",
        flush=True,
    )
    return outcomes


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
    """Persist SERP hit when URL or snippet contains a direct invite."""
    invite, source = _invite_from_hit(hit, norm)
    store_norm = norm
    if invite:
        store_norm = normalize_url(invite.url)

    junk = bool(
        JUNK_HINTS.search(" ".join(filter(None, [hit.url, hit.title or "", hit.snippet or ""])))
    )

    access = AccessStatus.JOIN if invite and not junk else AccessStatus.WATCH
    join_url = invite.url if invite and not junk else None
    return ExtractedCommunity(
        website=store_norm.website,
        canonical_key=store_norm.canonical_key,
        canonical_domain=store_norm.canonical_domain,
        platform=store_norm.platform,
        platform_id=store_norm.platform_id,
        name=hit.title or store_norm.canonical_domain,
        niche=niche,
        geo=scan_geo,
        join_url=join_url,
        access_status=access,
        value_tier=ValueTier.JUNK if junk else ValueTier.LOW,
        value_score=0 if junk else 25,
        source_queries=[hit.query] if hit.query else [],
        raw_signals={
            "serp_stub": True,
            "snippet": hit.snippet,
            "provider": hit.provider,
            **(
                {
                    "join_url_source": {
                        "rule": invite.rule,
                        "platform": invite.platform,
                        "from": source,
                        "hit_url": hit.url,
                    }
                }
                if invite
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
    harvest: bool = False,
    skip_enrich: bool = False,
) -> None:
    total = len(candidates)
    print(
        f"serp stubs start candidates={total} harvest={harvest} skip_enrich={skip_enrich}",
        flush=True,
    )
    for idx, (hit, norm) in enumerate(candidates, start=1):
        # Harvest every invite found in URL + title + snippet (directories/lists).
        blob = " ".join(filter(None, [hit.url or "", hit.title or "", hit.snippet or ""]))
        invites = find_all_invites_in_text(blob)
        direct = classify_invite_url(hit.url or "")
        if direct and all(i.url != direct.url for i in invites):
            invites = [direct, *invites]

        if not invites:
            if idx == 1 or idx == total or idx % 10 == 0:
                print(f"serp stubs {idx}/{total} (no invites)", flush=True)
            continue

        for invite in invites:
            item = _item_from_invite(
                invite.url,
                scan_geo=scan_geo,
                niche=niche,
                name=hit.title,
                source_queries=[hit.query] if hit.query else [],
                raw_signals={
                    "serp_stub": True,
                    "snippet": hit.snippet,
                    "provider": hit.provider,
                    "hit_url": hit.url,
                    **(
                        {"directory_size_text": hit.snippet}
                        if hit.provider == "directory" and hit.snippet
                        else {}
                    ),
                },
                harvest=harvest,
            )
            if item is None:
                continue
            _upsert_invite_item(
                session,
                item,
                metrics,
                harvest=harvest,
                skip_enrich=skip_enrich,
            )
        if idx == 1 or idx == total or idx % 5 == 0:
            print(
                f"serp stubs {idx}/{total} invites={len(invites)} "
                f"upserted_new={metrics.upserted_new}",
                flush=True,
            )
    print(f"serp stubs done upserted_new={metrics.upserted_new} rejects={metrics.reject_reasons}", flush=True)


def apply_outcomes(
    session: Session,
    outcomes: list[ProcessOutcome],
    metrics: PipelineMetrics,
    *,
    harvest: bool = False,
    skip_enrich: bool = False,
) -> None:
    total = len(outcomes)
    print(f"apply outcomes start items={total} harvest={harvest}", flush=True)
    for idx, outcome in enumerate(outcomes, start=1):
        if outcome.fetched:
            metrics.fetched += 1
        else:
            metrics.fetch_errors += 1
        metrics.llm_calls += outcome.llm_calls

        item = outcome.item
        invite_urls: list[str] = []
        for entry in item.raw_signals.get("all_invites") or []:
            if isinstance(entry, dict) and entry.get("url"):
                invite_urls.append(str(entry["url"]))
        if item.join_url:
            invite_urls.insert(0, item.join_url)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_urls: list[str] = []
        for url in invite_urls:
            key = url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            unique_urls.append(url)

        if not unique_urls:
            metrics.note_reject("no_invite_on_page")
            continue

        invite_meta = {
            str(e.get("url", "")).lower().rstrip("/"): e
            for e in (item.raw_signals.get("all_invites") or [])
            if isinstance(e, dict) and e.get("url")
        }
        for url in unique_urls:
            meta = invite_meta.get(url.lower().rstrip("/"), {})
            expanded = _item_from_invite(
                url,
                scan_geo=item.geo or "USA",
                niche=item.niche,
                name=(meta.get("anchor_text") or None) or item.name,
                source_queries=list(item.source_queries or []),
                raw_signals={
                    "from_page": item.website,
                    "source_canonical_key": item.canonical_key,
                    "anchor_text": meta.get("anchor_text"),
                    "invite_rule": meta.get("rule"),
                    **{k: v for k, v in (item.raw_signals or {}).items() if k != "all_invites"},
                },
                harvest=harvest,
            )
            if expanded is None:
                metrics.note_reject("invite_filtered")
                continue
            _upsert_invite_item(
                session,
                expanded,
                metrics,
                harvest=harvest,
                skip_enrich=skip_enrich,
            )
        if idx == 1 or idx == total or idx % 10 == 0:
            print(
                f"apply outcomes {idx}/{total} "
                f"upserted_new={metrics.upserted_new} skipped={metrics.skipped_junk} "
                f"rejects={metrics.reject_reasons}",
                flush=True,
            )
    print(
        f"apply outcomes done fetched={metrics.fetched} "
        f"upserted_new={metrics.upserted_new} skipped={metrics.skipped_junk} "
        f"rejects={metrics.reject_reasons}",
        flush=True,
    )


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

    ranked = sorted(
        unique.values(),
        key=lambda pair: _invite_priority(pair[0], pair[1]),
        reverse=True,
    )
    return hits, key_by_url, ranked, metrics


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
            apply_outcomes(
                session,
                outcomes,
                metrics,
                harvest=bool(settings.harvest_mode),
                skip_enrich=bool(settings.harvest_mode and settings.harvest_skip_enrich),
            )
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
        print(
            f"pipeline start niche={params.niche!r} geo={params.geo!r} "
            f"harvest={settings.harvest_mode} queries={query_limit} "
            f"per_query={per_query} max_fetch={max_fetch}",
            flush=True,
        )
        hits, key_by_url, unique_candidates, metrics = discover_candidates(
            settings,
            params,
            per_query=per_query,
            query_limit=query_limit,
        )
        print(
            f"normalize done hits={len(hits)} unique={len(unique_candidates)} "
            f"blocked={metrics.blocked}",
            flush=True,
        )
        save_discovery_hits(session, hits, key_by_url)

        llm_on = settings.llm_enabled if use_llm is None else use_llm
        scan_geo = resolve_geo(params.geo)
        harvest = bool(settings.harvest_mode)
        skip_enrich = bool(harvest and settings.harvest_skip_enrich)

        # Volume: write every unique SERP hit immediately, then enrich via fetch.
        apply_serp_stubs(
            session,
            unique_candidates[:max_fetch],
            metrics,
            scan_geo=scan_geo,
            niche=params.niche,
            harvest=harvest,
            skip_enrich=skip_enrich,
        )
        session.commit()
        print("serp stubs committed", flush=True)

        inline = unique_candidates[:max_fetch]
        overflow = unique_candidates[max_fetch:]

        outcomes = process_candidates_parallel(
            inline,
            settings,
            llm_on=llm_on,
            max_items=max_fetch,
            scan_geo=scan_geo,
        )
        apply_outcomes(
            session,
            outcomes,
            metrics,
            harvest=harvest,
            skip_enrich=skip_enrich,
        )

        if overflow and settings.use_fetch_queue:
            jobs = [
                fetch_job_from_candidate(hit, norm, geo=scan_geo)
                for hit, norm in overflow
            ]
            metrics.enqueued = enqueue_fetch_jobs(settings, jobs)

        _finalize_run(session, run_id, status="success", metrics=metrics)
        print(f"pipeline done run_id={run_id} metrics={metrics.as_dict()}", flush=True)
        return PipelineResult(metrics=metrics, run_id=run_id)
    except Exception as exc:  # noqa: BLE001
        _finalize_run(session, run_id, status="error", metrics=metrics, error=str(exc))
        raise
