from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from community_scanner.likelihood import community_likelihood
from community_scanner.models import (
    CommunityRow,
    DiscoveryHit,
    DiscoveryResultRow,
    ExtractedCommunity,
    RawCandidateRow,
)
from community_scanner.normalize import normalize_url


def make_engine(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        Path("data").mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def make_session_factory(database_url: str):
    return sessionmaker(bind=make_engine(database_url), autoflush=False, autocommit=False)


CHANGED_FIELDS = (
    "name",
    "join_url",
    "price_amount",
    "size_members",
    "access_status",
    "value_tier",
    "geo",
)


def save_discovery_hits(
    session: Session,
    hits: list[DiscoveryHit],
    canonical_keys: dict[str, str],
    *,
    batch_size: int = 500,
) -> int:
    """Write discovery_results in batches with progress logs (keeps DB responsive)."""
    total = len(hits)
    if total == 0:
        return 0
    print(f"discovery_results write start rows={total}", flush=True)
    written = 0
    batch: list[DiscoveryResultRow] = []
    for hit in hits:
        batch.append(
            DiscoveryResultRow(
                url=hit.url,
                title=hit.title,
                snippet=hit.snippet,
                provider=hit.provider,
                query=hit.query,
                canonical_key=canonical_keys.get(hit.url),
            )
        )
        if len(batch) >= batch_size:
            session.add_all(batch)
            session.flush()
            written += len(batch)
            print(f"discovery_results {written}/{total}", flush=True)
            batch = []
    if batch:
        session.add_all(batch)
        session.flush()
        written += len(batch)
        print(f"discovery_results {written}/{total}", flush=True)
    return written


def _source_record_id(hit: DiscoveryHit, canonical_key: str | None) -> str:
    if canonical_key:
        return canonical_key[:512]
    digest = hashlib.sha1(hit.url.encode("utf-8", errors="ignore")).hexdigest()
    return f"url:{digest}"


def upsert_raw_candidates(
    session: Session,
    hits: list[DiscoveryHit],
    *,
    min_likelihood: float = 0.0,
    batch_size: int = 300,
) -> dict[str, int]:
    """Persist bulk discovery hits into raw_candidates (batched, no per-row SELECT)."""
    stats = {"seen": 0, "inserted": 0, "skipped_low": 0, "dup": 0}
    bind = session.get_bind()
    dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
    now = datetime.now(timezone.utc)
    pending: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    def _flush_pending() -> None:
        nonlocal pending
        if not pending:
            return
        chunk = pending
        pending = []
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(RawCandidateRow)
                .values(chunk)
                .on_conflict_do_nothing(constraint="uq_raw_candidates_source_record")
            )
            result = session.execute(stmt)
            # rowcount is inserts only when available
            inserted = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else len(chunk)
            stats["inserted"] += max(0, inserted)
            stats["dup"] += max(0, len(chunk) - max(0, inserted))
        else:
            for row in chunk:
                try:
                    with session.begin_nested():
                        session.add(RawCandidateRow(**row))
                        session.flush()
                    stats["inserted"] += 1
                except IntegrityError:
                    stats["dup"] += 1
        session.flush()

    print(f"raw_candidates write start hits={len(hits)}", flush=True)
    for hit in hits:
        stats["seen"] += 1
        if not hit.url:
            continue
        score = community_likelihood(hit.url, title=hit.title, snippet=hit.snippet)
        if score < min_likelihood:
            stats["skipped_low"] += 1
            continue
        norm = normalize_url(hit.url)
        canonical_key = None if norm.is_blocked else norm.canonical_key
        platform = None if norm.is_blocked else norm.platform.value
        platform_id = None if norm.is_blocked else norm.platform_id
        source_id = _source_record_id(hit, canonical_key)
        dedupe = (hit.provider, source_id)
        if dedupe in seen_keys:
            stats["dup"] += 1
            continue
        seen_keys.add(dedupe)
        payload_hash = hashlib.sha1(
            f"{hit.provider}|{hit.url}|{hit.query or ''}".encode()
        ).hexdigest()
        pending.append(
            {
                "id": str(uuid4()),
                "url": hit.url,
                "canonical_key": canonical_key,
                "platform": platform,
                "platform_id": platform_id,
                "source_provider": hit.provider,
                "source_record_id": source_id,
                "title": hit.title,
                "snippet": hit.snippet,
                "raw_payload_hash": payload_hash,
                "community_likelihood": score,
                "status": "normalized" if canonical_key else "new",
                "discovered_at": now,
            }
        )
        if len(pending) >= batch_size:
            _flush_pending()
            print(f"raw_candidates progress seen={stats['seen']} inserted={stats['inserted']}", flush=True)
    _flush_pending()
    return stats


def _pending_community(session: Session, canonical_key: str) -> CommunityRow | None:
    """Return an unflushed insert in this session (same transaction duplicate guard)."""
    for obj in session.new:
        if isinstance(obj, CommunityRow) and obj.canonical_key == canonical_key:
            return obj
    return None


def upsert_community(session: Session, item: ExtractedCommunity) -> tuple[CommunityRow, bool, bool]:
    """Returns (row, created, changed)."""
    existing = _pending_community(session, item.canonical_key)
    if existing is None:
        existing = session.scalar(
            select(CommunityRow).where(CommunityRow.canonical_key == item.canonical_key)
        )
    now = datetime.now(timezone.utc)

    if existing is None:
        row = CommunityRow(
            canonical_key=item.canonical_key,
            canonical_domain=item.canonical_domain,
            platform=item.platform.value,
            platform_id=item.platform_id,
            website=item.website,
            name=item.name,
            niche=item.niche,
            audience=item.audience,
            geo=item.geo,
            join_url=item.join_url,
            price_text=item.price_text,
            price_amount=item.price_amount,
            currency=item.currency,
            size_text=item.size_text,
            size_members=item.size_members,
            contacts=item.contacts,
            access_status=item.access_status.value,
            value_score=item.value_score,
            value_tier=item.value_tier.value,
            relevance_score=item.relevance_score,
            source_queries=item.source_queries,
            raw_signals=item.raw_signals,
            content_hash=item.content_hash,
            sync_status="pending",
            first_seen_at=now,
            last_seen_at=now,
            last_changed_at=now,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row, True, True
        except IntegrityError:
            # Parallel workers may race on the same canonical_key.
            existing = session.scalar(
                select(CommunityRow).where(CommunityRow.canonical_key == item.canonical_key)
            )
            if existing is None:
                raise
            now = datetime.now(timezone.utc)

    changed = False
    for field in CHANGED_FIELDS:
        new_val = getattr(item, field)
        if hasattr(new_val, "value"):
            new_val = new_val.value
        old_val = getattr(existing, field)
        if new_val != old_val and new_val is not None:
            setattr(existing, field, new_val)
            changed = True

    existing.last_seen_at = now
    existing.raw_signals = item.raw_signals
    existing.source_queries = list({*existing.source_queries, *item.source_queries})
    if item.content_hash and item.content_hash != existing.content_hash:
        existing.content_hash = item.content_hash
        changed = True
    if changed:
        existing.last_changed_at = now
        existing.sync_status = "pending"
    return existing, False, changed
