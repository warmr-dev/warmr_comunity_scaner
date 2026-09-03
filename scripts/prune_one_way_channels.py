"""Remove Telegram pages explicitly identified as one-way channels.

Unknown or blocked pages are kept. A row is removed only when Telegram's page
contains clear channel markers such as "subscribers" or "Go to Channel".
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

CHANNEL_MARKERS = (
    "subscribers",
    "subscriber",
    "go to channel",
    "telegram channel",
    "channel statistics",
)
GROUP_MARKERS = ("members", "join group", "group chat", "group invite")


def inspect(row: tuple) -> tuple[tuple, bool, str]:
    row_id, url = row
    if not url or "/+" in url or "joinchat/" in url.lower():
        return row, False, "private_invite_or_unknown"
    try:
        with httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible; WarmrChannelAudit/1.0)"},
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            response = client.get(url)
        if response.status_code >= 400:
            return row, False, f"http_{response.status_code}"
        body = (response.text or "")[:100_000].lower()
        channels = [marker for marker in CHANNEL_MARKERS if marker in body]
        groups = [marker for marker in GROUP_MARKERS if marker in body]
        if channels and not groups:
            return row, True, f"markers:{','.join(channels)}"
        return row, False, "group_or_unclear"
    except Exception as exc:  # noqa: BLE001
        return row, False, f"fetch_error:{type(exc).__name__}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, join_url
                FROM community_scanner
                WHERE platform = 'telegram'
                  AND join_url IS NOT NULL
                ORDER BY id
                """
            )
        ).fetchall()

    channel_ids: list[str] = []
    reasons: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(inspect, row) for row in rows]
        for future in as_completed(futures):
            row, is_channel, reason = future.result()
            reasons[reason.split(":", 1)[0]] = reasons.get(reason.split(":", 1)[0], 0) + 1
            if is_channel:
                channel_ids.append(row[0])
                print(f"CHANNEL\t{row[0]}\t{row[1]}\t{reason}", flush=True)

    print(f"scanned={len(rows)} one_way_channels={len(channel_ids)}")
    for reason, count in sorted(reasons.items()):
        print(f"  {reason}={count}")
    if args.dry_run or not channel_ids:
        return 0

    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM community_scanner WHERE id = ANY(:ids)"),
            {"ids": channel_ids},
        ).rowcount or 0
        remaining = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
    print(f"deleted={deleted} remaining={remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
