from __future__ import annotations

"""
Sync adapter: push cleaned communities into Warmr DB.

Until WARMR_DATABASE_URL + schema mapping are confirmed, this logs the payload
contract and marks rows skipped/synced locally.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from community_scanner.models import CommunityRow, SyncStatus


def community_to_warmr_payload(row: CommunityRow) -> dict:
    return {
        "external_id": row.id,
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
        "price_amount": row.price_amount,
        "currency": row.currency,
        "size_members": row.size_members,
        "contacts": row.contacts,
        "access_status": row.access_status,
        "value_score": row.value_score,
        "value_tier": row.value_tier,
        "source": "community_scanner",
        "content_hash": row.content_hash,
        "discovered_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
        "changed_at": row.last_changed_at.isoformat() if row.last_changed_at else None,
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
