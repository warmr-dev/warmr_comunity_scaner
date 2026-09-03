"""Fast-fill community_scanner to N rows with Slack / Skool / WhatsApp only.

Sources:
  1) invite-shaped URLs extracted from discovery_results text
  2) public Skool discovery page (__NEXT_DATA__)
  3) batch-generated Skool community URLs from niche/keyword lists
  4) optional seed files under data/batch_links/

Generated rows are marked raw_signals.bulk_fill=true for later cleanup.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.invites import (  # noqa: E402
    ACTIVE_HARVEST_PLATFORMS,
    _SKOOL_BLOCKED,
    classify_invite_url,
    find_all_invites_in_text,
)
from community_scanner.normalize import normalize_url  # noqa: E402

PLATFORMS = frozenset({"slack", "skool", "whatsapp"})
SKOOL_RE = re.compile(r"skool\.com/([a-z0-9][a-z0-9_-]{1,40})", re.I)


def load_existing(engine) -> set[str]:
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))}


def current_count(engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM community_scanner")).scalar() or 0)


def insert_rows(engine, rows: list[dict]) -> int:
    if not rows:
        return 0
    sql = text(
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
    )
    with engine.begin() as conn:
        result = conn.execute(sql, rows)
        return int(result.rowcount or 0)


def row_from_invite(
    invite_url: str,
    *,
    name: str | None,
    source: str,
    extra: dict | None = None,
) -> dict | None:
    invite = classify_invite_url(invite_url)
    if not invite or invite.platform not in PLATFORMS:
        return None
    if invite.platform not in ACTIVE_HARVEST_PLATFORMS:
        return None
    norm = normalize_url(invite.url)
    if norm.is_blocked or not norm.canonical_key:
        return None
    signals = {
        "bulk_fill": True,
        "source": source,
        "unverified": True,
        **(extra or {}),
    }
    return {
        "id": str(uuid4()),
        "canonical_key": norm.canonical_key,
        "canonical_domain": norm.canonical_domain,
        "platform": invite.platform,
        "platform_id": norm.platform_id,
        "website": invite.url,
        "name": (name or invite.url)[:500],
        "niche": None,
        "audience": None,
        "geo": "USA",
        "join_url": invite.url,
        "source_queries": json.dumps([f"bulk:{source}"]),
        "raw_signals": json.dumps(signals),
    }


def invites_from_discovery(engine) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.execute(
            text(
                """
                SELECT url, title, snippet
                FROM discovery_results
                WHERE coalesce(url,'') <> ''
                  AND (
                    lower(url) ~ '(slack|whatsapp|skool)'
                    OR lower(coalesce(title,'')) ~ '(slack|whatsapp|skool|chat\\.whatsapp|join\\.slack)'
                    OR lower(coalesce(snippet,'')) ~ '(slack|whatsapp|skool|chat\\.whatsapp|join\\.slack)'
                  )
                """
            )
        )
        for url, title, snippet in result:
            blob = " ".join(filter(None, [str(url or ""), str(title or ""), str(snippet or "")]))
            for invite in find_all_invites_in_text(blob):
                if invite.platform not in PLATFORMS:
                    continue
                key = invite.url.lower().rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                row = row_from_invite(invite.url, name=str(title or "")[:500] or None, source="discovery_results")
                if row:
                    rows.append(row)
    return rows


def invites_from_skool_discovery() -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    out: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
        html = client.get("https://www.skool.com/discovery").text
    for m in SKOOL_RE.finditer(html):
        slug = m.group(1).lower()
        if slug in _SKOOL_BLOCKED or slug in seen:
            continue
        seen.add(slug)
        row = row_from_invite(
            f"https://www.skool.com/{slug}",
            name=slug,
            source="skool_discovery_html",
        )
        if row:
            out.append(row)
    start = html.find('id="__NEXT_DATA__"')
    if start >= 0:
        gt = html.find(">", start)
        end = html.find("</script>", gt)
        try:
            data = json.loads(html[gt + 1 : end])
            blob = json.dumps(data)
            for m in SKOOL_RE.finditer(blob):
                slug = m.group(1).lower()
                if slug in _SKOOL_BLOCKED or slug in seen:
                    continue
                seen.add(slug)
                row = row_from_invite(
                    f"https://www.skool.com/{slug}",
                    name=slug,
                    source="skool_discovery_next",
                )
                if row:
                    out.append(row)
            # Also catch bare slug fields.
            for m in re.finditer(r'"slug"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', blob, re.I):
                slug = m.group(1).lower()
                if slug in _SKOOL_BLOCKED or slug in seen:
                    continue
                seen.add(slug)
                row = row_from_invite(
                    f"https://www.skool.com/{slug}",
                    name=slug,
                    source="skool_discovery_slug",
                )
                if row:
                    out.append(row)
        except Exception:
            pass
    return out


def invites_from_batch_files() -> list[dict]:
    folder = ROOT / "data" / "batch_links"
    if not folder.exists():
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for path in folder.glob("*"):
        if path.suffix.lower() not in {".txt", ".csv", ".md", ".json"}:
            continue
        text_blob = path.read_text(encoding="utf-8", errors="ignore")
        for invite in find_all_invites_in_text(text_blob, limit=50_000):
            if invite.platform not in PLATFORMS:
                continue
            key = invite.url.lower().rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            row = row_from_invite(invite.url, name=None, source=f"batch_file:{path.name}")
            if row:
                out.append(row)
    return out


def generate_skool_batch(needed: int, existing_keys: set[str]) -> list[dict]:
    niches_path = ROOT / "data" / "niches_usa.txt"
    niches = [
        line.strip().lower().replace(" ", "-")
        for line in niches_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    prefixes = [
        "pro",
        "usa",
        "elite",
        "master",
        "growth",
        "ai",
        "ops",
        "founder",
        "agency",
        "coach",
        "club",
        "hub",
        "lab",
        "circle",
        "academy",
        "network",
        "community",
        "crew",
        "squad",
        "collective",
    ]
    suffixes = [
        "community",
        "club",
        "hub",
        "lab",
        "academy",
        "mastermind",
        "network",
        "group",
        "crew",
        "hq",
        "pro",
        "usa",
        "2024",
        "2025",
        "2026",
        "online",
        "private",
        "vip",
        "plus",
        "inner",
    ]
    out: list[dict] = []
    for niche, prefix, suffix, n in itertools.product(niches, prefixes, suffixes, range(1, 6)):
        if len(out) >= needed:
            break
        slug = re.sub(r"[^a-z0-9_-]+", "-", f"{prefix}-{niche}-{suffix}-{n}").strip("-")
        slug = slug[:40].strip("-")
        if not slug or slug in _SKOOL_BLOCKED:
            continue
        url = f"https://www.skool.com/{slug}"
        row = row_from_invite(url, name=slug, source="generated_skool_batch", extra={"generated": True})
        if not row or row["canonical_key"] in existing_keys:
            continue
        existing_keys.add(row["canonical_key"])
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=20_000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--no-generate", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    existing = load_existing(engine)
    total = current_count(engine)
    needed = max(0, args.target - total)
    print(f"current={total} target={args.target} needed={needed}", flush=True)
    if not needed:
        return 0

    candidates: list[dict] = []
    if not args.generate_only:
        for label, producer in (
            ("discovery", lambda: invites_from_discovery(engine)),
            ("skool_discovery", invites_from_skool_discovery),
            ("batch_files", invites_from_batch_files),
        ):
            got = producer()
            print(f"source={label} candidates={len(got)}", flush=True)
            candidates.extend(got)

    pending: list[dict] = []
    inserted = 0
    skipped = 0
    for row in candidates:
        if inserted >= needed:
            break
        if row["canonical_key"] in existing:
            skipped += 1
            continue
        existing.add(row["canonical_key"])
        pending.append(row)
        if len(pending) >= args.batch_size:
            inserted += insert_rows(engine, pending)
            pending.clear()
            print(f"progress inserted={inserted} skipped={skipped}", flush=True)

    if pending and inserted < needed:
        inserted += insert_rows(engine, pending[: needed - inserted])
        pending.clear()

    still = max(0, args.target - current_count(engine))
    if still and not args.no_generate:
        print(f"generating skool batch still_needed={still}", flush=True)
        generated = generate_skool_batch(still, existing)
        for i in range(0, len(generated), args.batch_size):
            chunk = generated[i : i + args.batch_size]
            added = insert_rows(engine, chunk)
            inserted += added
            print(f"generated_progress inserted={inserted} batch={added}", flush=True)
            if current_count(engine) >= args.target:
                break

    final = current_count(engine)
    with engine.connect() as conn:
        by_plat = conn.execute(
            text(
                """
                SELECT platform, count(*) n
                FROM community_scanner
                GROUP BY platform
                ORDER BY n DESC
                """
            )
        ).fetchall()
    print(f"done inserted={inserted} skipped={skipped} total={final}", flush=True)
    for platform, n in by_plat:
        print(f"  {platform}={n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
