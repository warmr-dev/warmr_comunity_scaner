"""Keep only valid, useful community invite rows in community_scanner.

Policy (Warmr):
  KEEP platforms: whatsapp, skool, circle, slack
  KEEP only if join_url classifies as a real invite on that platform
  DROP telegram/discord/custom, russian-flagged, adult, system hosts,
       listicle/guide titles, bad platform_ids, join_url duplicates

Usage:
  .venv\\Scripts\\python.exe scripts\\prune_valid_only.py --dry-run
  .venv\\Scripts\\python.exe scripts\\prune_valid_only.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.content_filter import is_adult_community  # noqa: E402
from community_scanner.invites import (  # noqa: E402
    ACTIVE_HARVEST_PLATFORMS,
    _CIRCLE_BLOCKED,
    _SKOOL_BLOCKED,
    _SLACK_SYSTEM_HOSTS,
    classify_invite_url,
)

KEEP_PLATFORMS = frozenset(
    {"whatsapp", "skool", "circle", "slack", "telegram", "facebook", "linkedin"}
)

LISTICLE_NAME_RE = re.compile(
    r"(?:"
    r"^https?://"
    r"|^\s*$"
    r"|list of\b"
    r"|how to (?:start|create|make|send|get|fix|remove|run|watch|view|win|build)\b"
    r"|full guide\b"
    r"|step[- ]by[- ]step\b"
    r"|discord servers\b"
    r"|all discord\b"
    r"|best telegram\b"
    r"|top\s*\d+"
    r"|telegram search\b"
    r"|assets-v3\.circle\.so"
    r"|\bpdf\b"
    r"|download\b"
    r"|converter\b"
    r"|unlock\s*tool"
    r"|\bapk\b"
    r"|\bhack\b"
    r"|betting\b"
    r"|casino\b"
    r"|forex\s*signal"
    r"|crypto\s*signal"
    r"|free\s*followers"
    r"|^instagram$"
    r"|scheme\s*of\s*work"
    r"|syllabus\b"
    r"|coupon\b"
    r"|gb\s*whatsapp"
    r"|whatsapp\s*gb"
    r"|followers$"
    r"|ilovepdf"
    r"|capital casino"
    r"|11 proven strategies"
    r"|cdn-marketing\.circle"
    r")",
    re.I,
)

BAD_PLATFORM_IDS = frozenset(
    {
        "username",
        "share",
        "joinchat",
        "invite",
        "discovery",
        "about",
        "login",
        "signup",
        "pricing",
        "explore",
        "search",
        "settings",
        "admin",
        "api",
        "help",
        "blog",
        "www",
        "app",
        "status",
        "circle",
        *{s.lower() for s in _SLACK_SYSTEM_HOSTS},
        *{s.lower() for s in _SKOOL_BLOCKED},
        *{s.lower() for s in _CIRCLE_BLOCKED},
    }
)


def reason_drop(row) -> str | None:
    platform = (row.platform or "").lower()
    join_url = (row.join_url or "").strip()
    website = (row.website or "").strip()
    name = (row.name or "").strip()
    platform_id = (row.platform_id or "").strip().lower()
    signals = row.raw_signals or {}

    if platform not in KEEP_PLATFORMS:
        return f"platform:{platform or 'none'}"

    if isinstance(signals, dict) and str(signals.get("maybe_russian", "")).lower() == "true":
        return "maybe_russian"

    if is_adult_community(name=name, url=join_url or website, platform_id=platform_id):
        return "adult"

    if platform_id and platform_id in BAD_PLATFORM_IDS:
        return f"bad_platform_id:{platform_id}"

    if name and LISTICLE_NAME_RE.search(name):
        return "listicle_name"

    invite = classify_invite_url(join_url) or classify_invite_url(website)
    if not invite:
        return "not_invite_shape"
    if invite.platform not in ACTIVE_HARVEST_PLATFORMS:
        return f"invite_platform:{invite.platform}"
    if invite.platform != platform:
        # Row platform drifted from actual invite URL.
        return f"platform_mismatch:{platform}->{invite.platform}"

    # Slack: only real invites (already enforced by classify).
    if platform == "slack" and invite.rule not in {"slack_shared_invite"}:
        return f"slack_rule:{invite.rule}"

    # Circle: only real tenant subdomains.
    if platform == "circle" and invite.rule != "circle_subdomain":
        return f"circle_rule:{invite.rule}"
    if platform == "circle" and "circle.so/c/" in (join_url or "").lower():
        return "circle_path_junk"
    if platform == "circle" and re.search(r"cdn|assets", (join_url or website or ""), re.I):
        return "circle_cdn"

    if row.size_members is not None and (row.size_members < 50 or row.size_members > 500_000):
        return f"bad_size:{row.size_members}"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, platform, platform_id, website, join_url, name,
                       size_members, canonical_key, raw_signals
                FROM community_scanner
                ORDER BY platform, platform_id
                """
            )
        ).mappings().all()

    if args.limit:
        rows = rows[: args.limit]

    drop_ids: list[str] = []
    reasons: dict[str, int] = {}
    for row in rows:
        why = reason_drop(row)
        if why:
            drop_ids.append(row["id"])
            key = why.split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1

    keep = len(rows) - len(drop_ids)
    print(f"scanned={len(rows)} keep={keep} drop={len(drop_ids)}")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {k}={v}")

    # Also find join_url duplicates among keepers.
    keep_rows = [r for r in rows if r["id"] not in set(drop_ids)]
    seen_join: dict[str, str] = {}
    dupe_ids: list[str] = []
    for r in keep_rows:
        j = (r["join_url"] or "").strip().rstrip("/").lower()
        if not j:
            continue
        if j in seen_join:
            # Prefer earlier (stable) row; drop this one.
            dupe_ids.append(r["id"])
        else:
            seen_join[j] = r["id"]
    print(f"join_url_dupes_among_keep={len(dupe_ids)}")
    drop_ids.extend(dupe_ids)
    drop_ids = list(dict.fromkeys(drop_ids))
    print(f"final_drop={len(drop_ids)} final_keep={len(rows) - len(drop_ids)}")

    if args.dry_run or not drop_ids:
        return 0

    with engine.begin() as conn:
        # Chunk deletes
        deleted = 0
        chunk = 500
        for i in range(0, len(drop_ids), chunk):
            part = drop_ids[i : i + chunk]
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
