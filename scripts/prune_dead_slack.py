"""Probe bare Slack workspace URLs and delete dead/system ones.

Usage (from repo root, with DATABASE_URL in .env):
  .venv\\Scripts\\python.exe scripts\\prune_dead_slack.py --dry-run
  .venv\\Scripts\\python.exe scripts\\prune_dead_slack.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.invites import _SLACK_SYSTEM_HOSTS  # noqa: E402

DEAD_MARKERS = (
    "there’s been a slight problem",
    "there's been a slight problem",
    "this workspace doesn’t exist",
    "this workspace doesn't exist",
    "team not found",
    "workspace not found",
    "invalid workspace",
    "find your workspace",
    "slauth login",
    "page not found",
)


def _is_dead(url: str, client: httpx.Client) -> tuple[bool, str]:
    try:
        r = client.get(url, follow_redirects=True, timeout=20.0)
    except Exception as exc:  # noqa: BLE001
        return True, f"fetch_error:{type(exc).__name__}"
    final = str(r.url).lower()
    text_lc = (r.text or "")[:8000].lower()
    if any(m in text_lc for m in DEAD_MARKERS):
        return True, "dead_marker"
    # 403/429 are bot defenses — not proof the workspace is dead.
    if r.status_code in {403, 429, 503}:
        return False, f"soft_{r.status_code}"
    if "dev.slack.com" in final:
        return True, f"redirect:{final[:80]}"
    if r.status_code >= 400:
        return True, f"http_{r.status_code}"
    return False, f"ok_{r.status_code}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    with engine.begin() as conn:
        # Always drop known system hosts first.
        system_sql = text(
            """
            DELETE FROM community_scanner
            WHERE platform = 'slack'
              AND lower(coalesce(platform_id, '')) = ANY(:ids)
            RETURNING id, platform_id, website
            """
        )
        deleted_system = conn.execute(system_sql, {"ids": list(_SLACK_SYSTEM_HOSTS)}).fetchall()
        print(f"system_hosts_deleted={len(deleted_system)}")

        # Deduplicate join_url (keep non-site canonical_key).
        dupe_sql = text(
            """
            WITH ranked AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       PARTITION BY lower(regexp_replace(join_url, '/$', ''))
                       ORDER BY
                         CASE WHEN canonical_key LIKE 'site:%' THEN 1 ELSE 0 END,
                         last_seen_at DESC NULLS LAST,
                         first_seen_at DESC NULLS LAST
                     ) AS rn
              FROM community_scanner
              WHERE join_url IS NOT NULL AND join_url <> ''
            )
            DELETE FROM community_scanner
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            RETURNING id
            """
        )
        if args.dry_run:
            preview = conn.execute(
                text(
                    """
                    WITH ranked AS (
                      SELECT id,
                             ROW_NUMBER() OVER (
                               PARTITION BY lower(regexp_replace(join_url, '/$', ''))
                               ORDER BY
                                 CASE WHEN canonical_key LIKE 'site:%' THEN 1 ELSE 0 END,
                                 last_seen_at DESC NULLS LAST
                             ) AS rn
                      FROM community_scanner
                      WHERE join_url IS NOT NULL AND join_url <> ''
                    )
                    SELECT count(*) FROM ranked WHERE rn > 1
                    """
                )
            ).scalar()
            print(f"dry_run join_url_dupes={preview}")
            conn.rollback()
        else:
            deleted_dupes = conn.execute(dupe_sql).fetchall()
            print(f"join_url_dupes_deleted={len(deleted_dupes)}")

        rows = conn.execute(
            text(
                """
                SELECT id, website, join_url, platform_id, canonical_key
                FROM community_scanner
                WHERE platform = 'slack'
                  AND coalesce(join_url, website) !~* 'join\\.slack\\.com/t/|/shared_invite/'
                ORDER BY platform_id
                """
            )
        ).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    print(f"probe_candidates={len(rows)}")
    dead_ids: list[str] = []
    with httpx.Client(headers={"User-Agent": "warmr-community-scanner/1.0"}, http2=False) as client:
        for row in rows:
            url = row.join_url or row.website
            dead, reason = _is_dead(url, client)
            mark = "DEAD" if dead else "ok"
            print(f"{mark}\t{row.platform_id}\t{url}\t{reason}")
            if dead:
                dead_ids.append(row.id)

    print(f"dead_found={len(dead_ids)}")
    if args.dry_run or not dead_ids:
        return 0

    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM community_scanner WHERE id = ANY(:ids) RETURNING id"),
            {"ids": dead_ids},
        ).fetchall()
        print(f"dead_deleted={len(deleted)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
