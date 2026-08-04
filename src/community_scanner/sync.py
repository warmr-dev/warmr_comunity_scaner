from __future__ import annotations

"""
Sync adapter: write cleaned communities into Warmr DB.

Goal: match Warmr "communities" table column names/shape (see communities.json export).
"""

from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, select
from sqlalchemy.orm import Session

from community_scanner.models import CommunityRow, SyncStatus


WARMRTABLE_COLUMNS: list[str] = [
    "id",
    "canonical_key",
    "canonical_domain",
    "platform",
    "platform_id",
    "website",
    "name",
    "niche",
    "audience",
    "geo",
    "join_url",
    "price_text",
    "price_amount",
    "currency",
    "size_text",
    "size_members",
    "contacts",
    "access_status",
    "value_score",
    "value_tier",
    "relevance_score",
    "source_queries",
    "raw_signals",
    "content_hash",
    "sync_status",
    "synced_at",
    "first_seen_at",
    "last_seen_at",
    "last_changed_at",
]


def community_to_warmr_payload(row: CommunityRow) -> dict:
    """
    Map our scanner row into Warmr "communities" table column set.

    Note: types (jsonb vs text) are handled by SQLAlchemy once we reflect the Warmr table.
    """
    return {
        "id": row.id,
        "canonical_key": row.canonical_key,
        "canonical_domain": row.canonical_domain,
        "platform": row.platform,
        "platform_id": row.platform_id,
        "website": row.website,
        "name": row.name,
        "niche": row.niche,
        "audience": row.audience,
        "geo": row.geo,
        "join_url": row.join_url,
        "price_text": row.price_text,
        "price_amount": row.price_amount,
        "currency": row.currency,
        "size_text": row.size_text,
        "size_members": row.size_members,
        "contacts": row.contacts,
        "access_status": row.access_status,
        "value_score": row.value_score,
        "value_tier": row.value_tier,
        "relevance_score": row.relevance_score,
        "source_queries": row.source_queries,
        "raw_signals": row.raw_signals,
        "content_hash": row.content_hash,
        "sync_status": row.sync_status,
        "synced_at": row.synced_at,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "last_changed_at": row.last_changed_at,
    }


def pending_sync_rows(session: Session, value_tiers: list[str]) -> list[CommunityRow]:
    stmt = select(CommunityRow).where(
        CommunityRow.sync_status == SyncStatus.PENDING.value,
        CommunityRow.value_tier.in_(value_tiers),
        CommunityRow.access_status != "reject",
    )
    return list(session.scalars(stmt))


def mark_synced(session: Session, row: CommunityRow) -> None:
    row.sync_status = SyncStatus.SYNCED.value
    row.synced_at = datetime.now(timezone.utc)


def dry_run_sync(session: Session, value_tiers: list[str]) -> list[dict]:
    """Prepare payloads; does not write to Warmr until adapter is wired."""
    payloads = []
    for row in pending_sync_rows(session, value_tiers):
        payloads.append(community_to_warmr_payload(row))
        # Until real Warmr write exists, keep pending (or mark skipped in dry-run CLI)
    return payloads


def sync_rows_to_warmr(
    scanner_session: Session,
    warmr_session: Session,
    value_tiers: list[str],
    *,
    warmr_table_name: str = "communities",
    upsert_key: str = "canonical_key",
) -> int:
    """
    Upsert rows into Warmr DB.

    Requires:
    - WARMR_DATABASE_URL points to PostgreSQL
    - Warmr table schema matches column names in WARMRTABLE_COLUMNS
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    warmr_engine = warmr_session.get_bind()
    meta = MetaData()
    warmr_table = Table(warmr_table_name, meta, autoload_with=warmr_engine)

    rows = pending_sync_rows(scanner_session, value_tiers)
    if not rows:
        return 0

    payloads = [community_to_warmr_payload(r) for r in rows]

    insert_stmt = pg_insert(warmr_table).values(payloads)
    update_cols = {c: getattr(insert_stmt.excluded, c) for c in WARMRTABLE_COLUMNS if c in warmr_table.c}
    if upsert_key not in warmr_table.c:
        raise ValueError(f"Warmr upsert key column not found: {upsert_key}")

    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[warmr_table.c[upsert_key]],
        set_=update_cols,
    )
    warmr_session.execute(upsert_stmt)
    warmr_session.commit()

    # Mark synced in scanner DB after successful Warmr upsert
    for r in rows:
        mark_synced(scanner_session, r)
    scanner_session.commit()
    return len(rows)
