from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from community_scanner.models import CommunityRow, DiscoveryHit, DiscoveryResultRow, ExtractedCommunity


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


def save_discovery_hits(session: Session, hits: list[DiscoveryHit], canonical_keys: dict[str, str]) -> int:
    rows = []
    for hit in hits:
        rows.append(
            DiscoveryResultRow(
                url=hit.url,
                title=hit.title,
                snippet=hit.snippet,
                provider=hit.provider,
                query=hit.query,
                canonical_key=canonical_keys.get(hit.url),
            )
        )
    session.add_all(rows)
    return len(rows)


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
