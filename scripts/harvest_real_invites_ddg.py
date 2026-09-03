"""Harvest real Slack / Skool / WhatsApp invite URLs via DuckDuckGo.

Upserts only classify_invite_url matches. No generated URLs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.discovery.ddg import DuckDuckGoProvider  # noqa: E402
from community_scanner.invites import classify_invite_url, find_all_invites_in_text  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

PLATFORMS = frozenset({"slack", "skool", "whatsapp"})


def build_queries(niches: list[str], limit: int) -> list[str]:
    base = [
        "inurl:chat.whatsapp.com",
        '"chat.whatsapp.com/" group OR community OR invite',
        "inurl:join.slack.com/t/",
        '"join.slack.com/t/" invite',
        '"shared_invite" site:slack.com',
        'site:github.com "join.slack.com/t/"',
        'site:github.com "chat.whatsapp.com"',
        'site:notion.so "join.slack.com"',
        'site:skool.com "members"',
        "site:skool.com community",
    ]
    niche_templates = [
        'inurl:chat.whatsapp.com "{niche}"',
        '"{niche}" "chat.whatsapp.com/"',
        'inurl:join.slack.com "{niche}"',
        '"{niche}" "join.slack.com/t/"',
        'site:skool.com "{niche}"',
        '"{niche}" site:skool.com community OR membership',
    ]
    out: list[str] = list(base)
    for niche in niches:
        term = niche.replace("-", " ")
        for tmpl in niche_templates:
            out.append(tmpl.format(niche=term))
            if len(out) >= limit:
                return out
    return out[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=int, default=80)
    parser.add_argument("--per-query", type=int, default=15)
    args = parser.parse_args()

    niches = [
        line.strip()
        for line in (ROOT / "data" / "niches_usa.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    queries = build_queries(niches, args.queries)
    ddg = DuckDuckGoProvider(delay=1.4)
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        existing = {row[0] for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))}

    pending: list[dict] = []
    seen_url: set[str] = set()
    inserted = 0

    def flush() -> int:
        nonlocal pending, inserted
        if not pending:
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
              '{}'::jsonb, 'join', 30, 'low',
              0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
            )
            ON CONFLICT (canonical_key) DO NOTHING
            """
        )
        with engine.begin() as conn:
            result = conn.execute(sql, pending)
            added = int(result.rowcount or 0)
        inserted += added
        pending.clear()
        return added

    for idx, query in enumerate(queries, start=1):
        try:
            hits = ddg.search(query, count=args.per_query)
        except Exception as exc:  # noqa: BLE001
            print(f"query_error {idx}/{len(queries)} {type(exc).__name__}: {exc}", flush=True)
            time.sleep(2.0)
            continue
        found_here = 0
        for hit in hits:
            blob = " ".join(filter(None, [hit.url or "", hit.title or "", hit.snippet or ""]))
            invites = find_all_invites_in_text(blob)
            direct = classify_invite_url(hit.url or "")
            if direct and all(i.url != direct.url for i in invites):
                invites = [direct, *invites]
            for invite in invites:
                if invite.platform not in PLATFORMS:
                    continue
                key = invite.url.lower().rstrip("/")
                if key in seen_url:
                    continue
                seen_url.add(key)
                norm = normalize_url(invite.url)
                if norm.is_blocked or norm.canonical_key in existing:
                    continue
                existing.add(norm.canonical_key)
                pending.append(
                    {
                        "id": str(uuid4()),
                        "canonical_key": norm.canonical_key,
                        "canonical_domain": norm.canonical_domain,
                        "platform": invite.platform,
                        "platform_id": norm.platform_id,
                        "website": invite.url,
                        "name": (hit.title or invite.url)[:500],
                        "niche": None,
                        "audience": None,
                        "geo": "USA",
                        "join_url": invite.url,
                        "source_queries": json.dumps([query]),
                        "raw_signals": json.dumps(
                            {
                                "source": "ddg_real_harvest",
                                "provider": "ddg",
                                "hit_url": hit.url,
                                "snippet": (hit.snippet or "")[:500],
                            }
                        ),
                    }
                )
                found_here += 1
        if len(pending) >= 100:
            flush()
        print(
            f"{idx}/{len(queries)} hits={len(hits)} invites={found_here} "
            f"pending={len(pending)} inserted={inserted}",
            flush=True,
        )

    flush()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM community_scanner")).scalar()
        by_plat = conn.execute(
            text("SELECT platform, count(*) n FROM community_scanner GROUP BY 1 ORDER BY n DESC")
        ).fetchall()
    print(f"done inserted={inserted} total={total}", flush=True)
    for p, n in by_plat:
        print(f"  {p}={n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
