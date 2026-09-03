"""Probe remaining community_scanner invites for explicit dead/invalid pages.

Does NOT treat HTTP 403/429 as dead (bot defenses).

Usage:
  .venv\\Scripts\\python.exe scripts\\probe_dead_invites.py --dry-run
  .venv\\Scripts\\python.exe scripts\\probe_dead_invites.py
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402

DEAD_MARKERS = (
    "invite link has been revoked",
    "invite link is invalid",
    "this invite link has expired",
    "invite expired",
    "group invite link is invalid",
    "can't join this group",
    "cannot join this group",
    "this group is no longer available",
    "this community is no longer available",
    "community not found",
    "page not found",
    "doesn't exist",
    "does not exist",
    "couldn't find that",
    "could not find that",
    "no longer available",
    "this invite may be expired",
    "workspace not found",
    "invalid invite",
    "invite invalid",
)


def probe(url: str, client: httpx.Client) -> tuple[bool, str]:
    try:
        r = client.get(url, follow_redirects=True, timeout=15.0)
    except Exception as exc:  # noqa: BLE001
        return False, f"fetch_error:{type(exc).__name__}"
    if r.status_code in {403, 429, 503}:
        return False, f"soft_{r.status_code}"
    body = (r.text or "")[:12000].lower()
    for marker in DEAD_MARKERS:
        if marker in body:
            return True, f"marker:{marker}"
    if r.status_code >= 400:
        return True, f"http_{r.status_code}"
    return False, f"ok_{r.status_code}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, platform, join_url, website, platform_id
                FROM community_scanner
                ORDER BY platform, id
                """
            )
        ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    dead_ids: list[str] = []
    soft = 0
    ok = 0
    errors = 0
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WarmrCommunityAudit/1.0)"}

    def job(row):
        url = row.join_url or row.website
        with httpx.Client(headers=headers, http2=False, follow_redirects=True) as client:
            return row, *probe(url, client)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(job, row) for row in rows]
        for fut in as_completed(futures):
            row, is_dead, reason = fut.result()
            done += 1
            if reason.startswith("soft_"):
                soft += 1
            elif reason.startswith("fetch_error"):
                errors += 1
            elif is_dead:
                dead_ids.append(row.id)
                print(f"DEAD\t{row.platform}\t{row.platform_id}\t{row.join_url}\t{reason}", flush=True)
            else:
                ok += 1
            if done % 200 == 0:
                print(
                    f"progress {done}/{len(rows)} dead={len(dead_ids)} soft={soft} ok={ok} err={errors}",
                    flush=True,
                )

    print(f"done scanned={len(rows)} dead={len(dead_ids)} soft={soft} ok={ok} err={errors}")
    if args.dry_run or not dead_ids:
        return 0

    with engine.begin() as conn:
        deleted = 0
        for i in range(0, len(dead_ids), 500):
            part = dead_ids[i : i + 500]
            res = conn.execute(
                text("DELETE FROM community_scanner WHERE id = ANY(:ids)"),
                {"ids": part},
            )
            deleted += res.rowcount or 0
        left = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
        by_plat = conn.execute(
            text("SELECT platform, count(*) n FROM community_scanner GROUP BY 1 ORDER BY n DESC")
        ).fetchall()
        print(f"deleted={deleted} remaining={left}")
        for p, n in by_plat:
            print(f"  {p}={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
