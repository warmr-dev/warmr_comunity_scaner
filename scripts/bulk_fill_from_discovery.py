"""Bulk-fill community_scanner from previously collected discovery_results.

This is intentionally permissive: it imports real URLs already present in the
database, even when they are not currently proven live community links.
Every imported row is marked raw_signals.bulk_import=true for later cleanup.

Usage:
  .venv\Scripts\python.exe scripts\bulk_fill_from_discovery.py --target 20000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.invites import classify_invite_url  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=20_000)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        current = int(conn.execute(text("SELECT count(*) FROM community_scanner")).scalar() or 0)
        existing = {
            row[0]
            for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))
        }
    needed = max(0, args.target - current)
    print(f"current={current} target={args.target} needed={needed}", flush=True)
    if not needed:
        return 0

    inserted = 0
    scanned = 0
    skipped = 0
    pending: list[dict] = []
    seen = set(existing)

    def flush(rows: list[dict]) -> int:
        if not rows:
            return 0
        with engine.begin() as conn:
            done = 0
            for row in rows:
                result = conn.execute(
                    text(
                        """
                        INSERT INTO community_scanner (
                          id, canonical_key, canonical_domain, platform, platform_id,
                          website, name, niche, audience, geo, join_url,
                          contacts, access_status, value_score, value_tier,
                          relevance_score, source_queries, raw_signals, sync_status
                        ) VALUES (
                          :id, :canonical_key, :canonical_domain, :platform, :platform_id,
                          :website, :name, :niche, :audience, :geo, :join_url,
                          '{}'::jsonb, 'watch', 20, 'low',
                          0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
                        )
                        ON CONFLICT (canonical_key) DO NOTHING
                        """
                    ),
                    row,
                )
                done += result.rowcount or 0
        return done

    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.execute(
            text(
                """
                SELECT url, title, snippet
                FROM discovery_results
                WHERE url IS NOT NULL AND url <> ''
                ORDER BY created_at DESC NULLS LAST
                """
            )
        )
        for url, title, snippet in result:
            scanned += 1
            raw_url = str(url).strip()
            if not raw_url.lower().startswith(("http://", "https://")):
                skipped += 1
                continue
            norm = normalize_url(raw_url)
            if norm.is_blocked or norm.canonical_key in seen:
                skipped += 1
                continue

            invite = classify_invite_url(raw_url)
            name = str(title).strip()[:500] if title else None
            pending.append(
                {
                    "id": str(uuid4()),
                    "canonical_key": norm.canonical_key,
                    "canonical_domain": norm.canonical_domain,
                    "platform": getattr(norm.platform, "value", str(norm.platform)),
                    "platform_id": norm.platform_id,
                    "website": norm.website,
                    "name": name,
                    "niche": None,
                    "audience": None,
                    "geo": "USA",
                    "join_url": invite.url if invite else None,
                    "source_queries": json.dumps(["bulk:discovery_results"]),
                    "raw_signals": json.dumps(
                        {
                            "bulk_import": True,
                            "source": "discovery_results",
                            "snippet": str(snippet)[:1000] if snippet else None,
                            "invite_rule": invite.rule if invite else None,
                            "unverified": True,
                        }
                    ),
                }
            )
            seen.add(norm.canonical_key)

            if len(pending) >= args.batch_size:
                added = flush(pending)
                inserted += added
                pending.clear()
                print(
                    f"progress scanned={scanned} inserted={inserted} skipped={skipped}",
                    flush=True,
                )
                if inserted >= needed:
                    break

    if pending and inserted < needed:
        inserted += flush(pending[: needed - inserted])

    with engine.connect() as conn:
        total = int(conn.execute(text("SELECT count(*) FROM community_scanner")).scalar() or 0)
    print(f"done scanned={scanned} inserted={inserted} total={total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
