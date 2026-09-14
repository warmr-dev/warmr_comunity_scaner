"""Free-tier collector: multi-index Common Crawl + Hive → candidates.jsonl → SQL batches.

No paid APIs. Designed to push into Supabase via MCP/SQL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.discovery.hive import HiveIndexProvider  # noqa: E402
from community_scanner.discovery.base import QueryParams  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

OUT_DIR = ROOT / "data" / "free_fill"
CANDIDATES_PATH = OUT_DIR / "candidates.jsonl"
EXISTING_KEYS_PATH = OUT_DIR / "existing_keys.txt"
SQL_DIR = OUT_DIR / "sql_batches"
COLLINFO = "https://index.commoncrawl.org/collinfo.json"

PATTERNS = (
    "skool.com/*",
    "www.skool.com/*",
    "join.slack.com/t/*",
    "old.reddit.com/r/*",
    "reddit.com/r/*",
    "www.facebook.com/groups/*",
    "facebook.com/groups/*",
    "www.linkedin.com/groups/*",
    "circle.so/*",
)

UA = {"User-Agent": "WarmrFreeFill/1.0 (+community-scanner; free inventory expansion)"}


def load_existing(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}


def latest_indexes(client: httpx.Client, n: int = 16) -> list[tuple[str, str]]:
    data = client.get(COLLINFO).json()
    out = []
    for item in data[:n]:
        cdx = item.get("cdx-api")
        idx = item.get("id")
        if cdx and idx:
            out.append((idx, cdx))
    return out


def canonical_url(url: str) -> str | None:
    try:
        p = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    host = p.netloc.lower().removeprefix("www.")
    parts = [x for x in p.path.split("/") if x]
    skip = {
        "discovery", "about", "login", "signup", "pricing", "blog", "help", "api",
        "settings", "explore", "search", "robots.txt", "careers", "privacy", "terms",
        "popular", "all", "mod", "wiki",
    }
    if host.endswith("skool.com") and parts:
        slug = parts[0].lower()
        if slug in skip or len(slug) < 3:
            return None
        return f"https://www.skool.com/{slug}"
    if host == "join.slack.com" and len(parts) >= 2 and parts[0] == "t":
        ws = parts[1].lower()
        if "shared_invite" in parts:
            return f"https://join.slack.com{p.path.split('?')[0]}"
        return f"https://join.slack.com/t/{ws}"
    if "reddit.com" in host and len(parts) >= 2 and parts[0] == "r":
        name = parts[1]
        if name.lower() in skip:
            return None
        return f"https://www.reddit.com/r/{name}"
    if "facebook.com" in host and len(parts) >= 2 and parts[0] == "groups":
        gid = parts[1]
        if gid.lower() in skip:
            return None
        return f"https://www.facebook.com/groups/{gid}"
    if "linkedin.com" in host and len(parts) >= 2 and parts[0] == "groups":
        return f"https://www.linkedin.com/groups/{parts[1]}"
    if host.endswith("circle.so") and parts:
        slug = parts[0].lower()
        if slug in skip | {"br", "ai", "academy", "brand", "blog"}:
            return None
        return f"https://{host}/{slug}"
    return None


def fetch_cdx_page(
    client: httpx.Client,
    cdx_api: str,
    pattern: str,
    *,
    limit: int = 200,
    resume_key: str | None = None,
) -> tuple[list[str], str | None]:
    params = {
        "url": pattern,
        "output": "json",
        "fl": "url",
        "limit": str(limit),
        "showResumeKey": "true",
    }
    if resume_key:
        params["resumeKey"] = resume_key
    for attempt in range(1, 5):
        try:
            resp = client.get(cdx_api, params=params)
            if resp.status_code in {429, 502, 503}:
                time.sleep(attempt * 2.5)
                continue
            if resp.status_code == 404:
                return [], None
            resp.raise_for_status()
            lines = [ln.strip() for ln in resp.text.splitlines() if ln.strip()]
            urls: list[str] = []
            next_key = None
            # CDX with showResumeKey: records, then blank conceptually, then resume key line.
            # With fl=url each line may be a JSON string "\"http...\"" or object.
            for i, ln in enumerate(lines):
                if ln.startswith("{") or ln.startswith("["):
                    try:
                        obj = json.loads(ln)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict) and obj.get("url"):
                        urls.append(obj["url"])
                    elif isinstance(obj, str) and obj.startswith("http"):
                        urls.append(obj)
                elif ln.startswith('"') and ln.endswith('"'):
                    try:
                        val = json.loads(ln)
                        if isinstance(val, str) and val.startswith("http"):
                            urls.append(val)
                    except json.JSONDecodeError:
                        pass
                elif "://" not in ln and i == len(lines) - 1 and urls:
                    # trailing resume key
                    next_key = ln
                elif ln.startswith("http"):
                    urls.append(ln)
            if lines and not next_key and len(lines) > len(urls):
                # last non-url line is resume key
                last = lines[-1]
                if "://" not in last and not last.startswith("{") and not last.startswith('"'):
                    next_key = last
            return urls, next_key
        except httpx.HTTPError:
            time.sleep(attempt * 2.0)
    return [], None


def row_from_url(url: str, source: str, query: str) -> dict | None:
    clean = canonical_url(url)
    if not clean:
        return None
    norm = normalize_url(clean)
    if norm.is_blocked or not norm.canonical_key:
        return None
    if norm.platform.value in {"telegram", "discord"}:
        return None
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()),
        "canonical_key": norm.canonical_key,
        "canonical_domain": norm.canonical_domain,
        "platform": norm.platform.value,
        "platform_id": norm.platform_id,
        "website": norm.website,
        "name": (norm.platform_id or norm.canonical_domain)[:500],
        "niche": None,
        "audience": None,
        "geo": "USA",
        "join_url": norm.website,
        "access_status": "join",
        "value_score": 30,
        "value_tier": "low",
        "relevance_score": 0.35,
        "contacts": {},
        "source_queries": [query],
        "raw_signals": {"source": source, "free_fill": True},
        "sync_status": "pending",
        "first_seen_at": now,
        "last_seen_at": now,
    }


def collect(target: int, indexes: int, pages_per_pattern: int, delay: float) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_existing(EXISTING_KEYS_PATH)
    seen = set(existing)
    # also load already collected
    if CANDIDATES_PATH.exists():
        with CANDIDATES_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    seen.add(json.loads(line)["canonical_key"])
                except Exception:  # noqa: BLE001
                    pass
    written_before = len(seen) - len(existing)
    written = 0

    with httpx.Client(timeout=60.0, headers=UA, follow_redirects=True) as client:
        idxs = latest_indexes(client, n=indexes)
        print(f"indexes={len(idxs)} target_new={target} already_collected={written_before}", flush=True)
        with CANDIDATES_PATH.open("a", encoding="utf-8") as out:
            for idx_name, cdx in idxs:
                if written >= target:
                    break
                for pattern in PATTERNS:
                    if written >= target:
                        break
                    resume = None
                    for page in range(pages_per_pattern):
                        if written >= target:
                            break
                        if delay:
                            time.sleep(delay)
                        urls, resume = fetch_cdx_page(
                            client, cdx, pattern, limit=300, resume_key=resume
                        )
                        kept = 0
                        for url in urls:
                            row = row_from_url(url, "commoncrawl", f"{idx_name}:{pattern}")
                            if not row:
                                continue
                            key = row["canonical_key"]
                            if key in seen:
                                continue
                            seen.add(key)
                            out.write(json.dumps(row, ensure_ascii=False) + "\n")
                            written += 1
                            kept += 1
                            if written >= target:
                                break
                        print(
                            f"{idx_name} {pattern} page={page} urls={len(urls)} "
                            f"kept={kept} total_new={written}",
                            flush=True,
                        )
                        if not urls or not resume:
                            break

    if written < target:
        print("hive fill...", flush=True)
        hive = HiveIndexProvider(
            timeout=25.0,
            delay=0.2,
            max_detail_pages=1500,
            exclude_discord_telegram=True,
        )
        hits = hive.crawl(QueryParams(niche="harvest"), count=min(3000, target - written + 200))
        with CANDIDATES_PATH.open("a", encoding="utf-8") as out:
            for hit in hits:
                if written >= target:
                    break
                row = row_from_url(hit.url, "hive", hit.query or "hive")
                if not row:
                    continue
                if row["canonical_key"] in seen:
                    continue
                seen.add(row["canonical_key"])
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1

    print(f"collect done new={written} file={CANDIDATES_PATH}", flush=True)
    return written


def sql_escape(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return "'" + text.replace("'", "''") + "'"


def emit_sql(batch_size: int = 120) -> int:
    if not CANDIDATES_PATH.exists():
        raise SystemExit("run collect first")
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    for old in SQL_DIR.glob("*.sql"):
        old.unlink()
    batch: list[dict] = []
    files = 0
    total = 0

    def flush() -> None:
        nonlocal batch, files, total
        if not batch:
            return
        files += 1
        vals = []
        for row in batch:
            vals.append(
                "("
                + ", ".join(
                    [
                        sql_escape(row["id"]),
                        sql_escape(row["canonical_key"]),
                        sql_escape(row["canonical_domain"]),
                        sql_escape(row["platform"]),
                        sql_escape(row["platform_id"]),
                        sql_escape(row["website"]),
                        sql_escape(row["name"]),
                        sql_escape(row["geo"]),
                        sql_escape(row["join_url"]),
                        sql_escape(row["access_status"]),
                        sql_escape(row["value_score"]),
                        sql_escape(row["value_tier"]),
                        sql_escape(row["relevance_score"]),
                        sql_escape(row["contacts"]) + "::jsonb",
                        sql_escape(row["source_queries"]) + "::jsonb",
                        sql_escape(row["raw_signals"]) + "::jsonb",
                        sql_escape(row["sync_status"]),
                        sql_escape(row["first_seen_at"]) + "::timestamptz",
                        sql_escape(row["last_seen_at"]) + "::timestamptz",
                    ]
                )
                + ")"
            )
        sql = (
            "insert into public.community_scanner (\n"
            "  id, canonical_key, canonical_domain, platform, platform_id, website, name,\n"
            "  geo, join_url, access_status, value_score, value_tier, relevance_score,\n"
            "  contacts, source_queries, raw_signals, sync_status, first_seen_at, last_seen_at\n"
            ") values\n"
            + ",\n".join(vals)
            + "\non conflict (canonical_key) do nothing;\n"
        )
        (SQL_DIR / f"batch_{files:04d}.sql").write_text(sql, encoding="utf-8")
        total += len(batch)
        batch = []

    with CANDIDATES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            batch.append(json.loads(line))
            if len(batch) >= batch_size:
                flush()
        flush()
    print(f"sql batches={files} rows={total}", flush=True)
    return files


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--target", type=int, default=90000)
    c.add_argument("--indexes", type=int, default=20)
    c.add_argument("--pages", type=int, default=30)
    c.add_argument("--delay", type=float, default=1.2)
    s = sub.add_parser("emit-sql")
    s.add_argument("--batch-size", type=int, default=120)
    args = parser.parse_args()
    if args.cmd == "collect":
        collect(args.target, args.indexes, args.pages, args.delay)
    else:
        emit_sql(args.batch_size)


if __name__ == "__main__":
    main()
