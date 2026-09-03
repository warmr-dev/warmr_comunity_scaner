"""Restore valid Telegram/Discord invites from discovery_results into community_scanner.

Pulls invite URLs from discovery url/title/snippet, classifies, probes, upserts.

Usage:
  .venv\\Scripts\\python.exe scripts\\restore_tg_discord.py --dry-run
  .venv\\Scripts\\python.exe scripts\\restore_tg_discord.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.content_filter import is_adult_community  # noqa: E402
from community_scanner.invites import classify_invite_url, find_all_invites_in_text  # noqa: E402
from community_scanner.language_filter import is_russian_community  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

TG_INVALID = (
    "sorry, this channel doesn't seem to exist",
    "this invite link is invalid",
    "invite link is invalid or has expired",
)
LISTICLE_TITLE = re.compile(
    r"(list of|how to|best telegram|best discord|top\s*\d+|discord servers|all discord)",
    re.I,
)


def _discord_code(url: str) -> str | None:
    m = re.search(r"(?:discord\.gg|discord\.com/invite)/([A-Za-z0-9_-]+)", url, re.I)
    return m.group(1) if m else None


def probe_invite(invite_url: str, platform: str, client: httpx.Client) -> tuple[bool, str, dict]:
    enrich: dict = {}
    if platform == "discord":
        code = _discord_code(invite_url)
        if not code:
            return False, "no_code", enrich
        try:
            r = client.get(
                f"https://discord.com/api/v9/invites/{code}",
                params={"with_counts": "true", "with_expiration": "true"},
                timeout=15.0,
            )
        except Exception as exc:  # noqa: BLE001
            return True, f"soft_fetch:{type(exc).__name__}", enrich
        if r.status_code in {403, 429, 503}:
            return True, f"soft_{r.status_code}", enrich
        if r.status_code == 404:
            return False, "discord_404", enrich
        if r.status_code >= 400:
            return False, f"http_{r.status_code}", enrich
        data = r.json() if r.content else {}
        msg = str(data.get("message", "")).lower()
        if "unknown invite" in msg:
            return False, "unknown_invite", enrich
        guild = data.get("guild") or {}
        enrich["name"] = guild.get("name") or (data.get("channel") or {}).get("name")
        enrich["size_members"] = data.get("approximate_member_count")
        if enrich.get("size_members"):
            enrich["size_text"] = f"{enrich['size_members']} members"
        return True, "ok_discord_api", enrich

    try:
        r = client.get(invite_url, follow_redirects=True, timeout=15.0)
    except Exception as exc:  # noqa: BLE001
        return True, f"soft_fetch:{type(exc).__name__}", enrich
    if r.status_code in {403, 429, 503}:
        return True, f"soft_{r.status_code}", enrich
    body = (r.text or "")[:15000].lower()
    if any(m in body for m in TG_INVALID):
        return False, "tg_invalid", enrich
    if r.status_code >= 400:
        return False, f"http_{r.status_code}", enrich
    if "tgme_page" not in body and "telegram" not in body:
        return False, "tg_not_preview", enrich
    m = re.search(r'og:title"\s+content="([^"]+)"', r.text or "", re.I)
    if m:
        enrich["name"] = m.group(1).strip()
    m = re.search(r"([\d\s,]+)\s+(members|subscribers)", body)
    if m:
        try:
            enrich["size_members"] = int(re.sub(r"[^\d]", "", m.group(1)))
            enrich["size_text"] = f"{enrich['size_members']} {m.group(2)}"
        except ValueError:
            pass
    return True, "ok_telegram", enrich


def extract_invites(url: str, title: str | None, snippet: str | None) -> list:
    blob = " ".join(filter(None, [url or "", title or "", snippet or ""]))
    found = find_all_invites_in_text(blob)
    direct = classify_invite_url(url or "")
    if direct and direct.platform in {"telegram", "discord"}:
        key = direct.url.lower().rstrip("/")
        if all(i.url.lower().rstrip("/") != key for i in found):
            found = [direct, *found]
    return [i for i in found if i.platform in {"telegram", "discord"}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--min-members", type=int, default=50)
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    sql = text(
        """
        SELECT url, title, snippet
        FROM discovery_results
        WHERE
          coalesce(title,'') ~* '(discord\\.gg/|discord\\.com/invite/|t\\.me/)'
          OR coalesce(snippet,'') ~* '(discord\\.gg/|discord\\.com/invite/|t\\.me/)'
          OR url ~* '(discord\\.gg/|discord\\.com/invite/|t\\.me/)'
        """
    )
    print("loading discovery rows…", flush=True)
    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()
    print(f"discovery_rows_with_invite_text={len(rows)}", flush=True)

    skip_reasons: dict[str, int] = {}
    candidates: dict[str, tuple] = {}

    for row in rows:
        invites = extract_invites(row.url, row.title, row.snippet)
        if not invites:
            skip_reasons["no_extract"] = skip_reasons.get("no_extract", 0) + 1
            continue
        for invite in invites:
            title = row.title
            if LISTICLE_TITLE.search(title or ""):
                skip_reasons["listicle_title"] = skip_reasons.get("listicle_title", 0) + 1
                continue
            if is_adult_community(name=title, url=invite.url):
                skip_reasons["adult"] = skip_reasons.get("adult", 0) + 1
                continue
            if is_russian_community(name=title, url=invite.url, source_url=row.url):
                skip_reasons["russian"] = skip_reasons.get("russian", 0) + 1
                continue
            norm = normalize_url(invite.url)
            if norm.is_blocked or not norm.platform_id:
                skip_reasons["blocked_or_no_id"] = skip_reasons.get("blocked_or_no_id", 0) + 1
                continue
            key = norm.canonical_key
            if key in candidates:
                skip_reasons["dup_canonical"] = skip_reasons.get("dup_canonical", 0) + 1
                continue
            candidates[key] = (invite, norm, title)
            if args.limit and len(candidates) >= args.limit:
                break
        if args.limit and len(candidates) >= args.limit:
            break

    print(f"unique_candidates={len(candidates)}")
    for k, v in sorted(skip_reasons.items(), key=lambda x: -x[1]):
        print(f"  skip_{k}={v}")

    with engine.connect() as conn:
        existing = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT canonical_key FROM community_scanner "
                    "WHERE platform IN ('telegram','discord')"
                )
            )
        }
    items = [v for k, v in candidates.items() if k not in existing]
    print(f"new_candidates={len(items)}")

    alive: list[tuple] = []
    dead = 0
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WarmrCommunityRestore/1.0)"}

    def job(item):
        invite, norm, title = item
        if args.skip_probe:
            return item, True, "skip_probe", {}
        with httpx.Client(headers=headers, http2=False, follow_redirects=True) as client:
            ok, reason, enrich = probe_invite(invite.url, invite.platform, client)
            return item, ok, reason, enrich

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(job, c) for c in items]
        for fut in as_completed(futs):
            item, ok, reason, enrich = fut.result()
            done += 1
            if ok:
                size = enrich.get("size_members")
                if size is not None and size < args.min_members:
                    dead += 1
                else:
                    alive.append((item, enrich))
            else:
                dead += 1
            if done % 300 == 0:
                print(
                    f"progress {done}/{len(items)} alive={len(alive)} rejected={dead}",
                    flush=True,
                )

    by_plat = {"telegram": 0, "discord": 0}
    for (invite, _n, _t), _e in alive:
        by_plat[invite.platform] = by_plat.get(invite.platform, 0) + 1
    print(f"probe_done alive={len(alive)} rejected={dead}")
    print(f"alive_telegram={by_plat['telegram']} alive_discord={by_plat['discord']}")

    if args.dry_run or not alive:
        return 0

    inserted = 0
    with engine.begin() as conn:
        for (invite, norm, title), enrich in alive:
            name = enrich.get("name") or title
            if name and LISTICLE_TITLE.search(name):
                name = None
            payload = {
                "id": str(uuid4()),
                "canonical_key": norm.canonical_key,
                "canonical_domain": norm.canonical_domain,
                "platform": invite.platform,
                "platform_id": norm.platform_id,
                "website": invite.url,
                "name": name,
                "geo": "USA",
                "join_url": invite.url,
                "size_text": enrich.get("size_text"),
                "size_members": enrich.get("size_members"),
                "access_status": "join",
                "value_score": 25,
                "value_tier": "low",
                "source_queries": json.dumps(["restore:discovery_results"]),
                "raw_signals": json.dumps(
                    {
                        "restored_from": "discovery_results",
                        "invite_rule": invite.rule,
                        "probe": True,
                    }
                ),
            }
            res = conn.execute(
                text(
                    """
                    INSERT INTO community_scanner (
                      id, canonical_key, canonical_domain, platform, platform_id, website, name,
                      geo, join_url, size_text, size_members, contacts, access_status,
                      value_score, value_tier, relevance_score, source_queries, raw_signals, sync_status
                    ) VALUES (
                      :id, :canonical_key, :canonical_domain, :platform, :platform_id, :website, :name,
                      :geo, :join_url, :size_text, :size_members, '{}'::jsonb, :access_status,
                      :value_score, :value_tier, 0, CAST(:source_queries AS jsonb),
                      CAST(:raw_signals AS jsonb), 'pending'
                    )
                    ON CONFLICT (canonical_key) DO NOTHING
                    """
                ),
                payload,
            )
            inserted += res.rowcount or 0

        totals = conn.execute(
            text(
                """
                SELECT platform, count(*) n FROM community_scanner
                GROUP BY 1 ORDER BY n DESC
                """
            )
        ).fetchall()
        print(f"inserted={inserted}")
        for p, n in totals:
            print(f"  {p}={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
