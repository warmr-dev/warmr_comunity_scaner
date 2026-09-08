"""Import a raw CSV, JSON, or TXT file with communities into community_scanner.

Features:
- Normalizes URL and extracts canonical_key/platform/canonical_domain automatically.
- Filters out blocked/junk domains and invalid records.
- Inserts with ON CONFLICT (canonical_key) DO NOTHING (idempotent, skips existing).
- Sets initial status to 'watch', value_score=20, value_tier='low'.

Supported formats:
- CSV: columns 'url' (or 'website'/'link'), optionally 'name', 'niche', 'geo', 'join_url', 'members', 'price'
- JSON: list of dicts with similar keys
- TXT: one URL per line
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.normalize import normalize_url  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def parse_file(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    items: list[dict] = []

    if suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("items") or data.get("communities") or [data]

    elif suffix in (".csv", ".tsv"):
        delimiter = "\t" if suffix == ".tsv" else ","
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                items.append(dict(row))

    elif suffix in (".txt", ""):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if raw and not raw.startswith("#"):
                    items.append({"url": raw})

    else:
        raise ValueError(f"Unsupported file format: {suffix} (expected .csv, .json, or .txt)")

    return items


def extract_url(item: dict) -> str:
    for key in ("url", "website", "link", "join_url", "community_url", "href"):
        val = item.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Import raw community records into community_scanner")
    parser.add_argument("file", type=str, help="Path to CSV, JSON, or TXT file")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for DB insert (default: 500)")
    parser.add_argument("--source", type=str, default="raw_import", help="Source tag for raw_signals (default: raw_import)")
    args = parser.parse_args()

    input_file = Path(args.file)
    if not input_file.exists():
        log.error(f"File not found: {input_file}")
        return 1

    log.info(f"Reading file: {input_file}")
    raw_items = parse_file(input_file)
    log.info(f"Loaded {len(raw_items)} records from file")

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    # Get set of already existing keys to avoid unnecessary processing
    with engine.connect() as conn:
        existing_keys = {
            row[0]
            for row in conn.execute(text("SELECT canonical_key FROM community_scanner"))
        }
    log.info(f"Existing canonical keys in DB: {len(existing_keys)}")

    seen_in_batch = set(existing_keys)
    valid_rows: list[dict] = []
    skipped_blocked = 0
    skipped_invalid_url = 0
    skipped_duplicates = 0

    for item in raw_items:
        raw_url = extract_url(item)
        if not raw_url:
            skipped_invalid_url += 1
            continue

        if not raw_url.lower().startswith(("http://", "https://")):
            raw_url = "https://" + raw_url

        norm = normalize_url(raw_url)
        if not norm.canonical_key or norm.is_blocked:
            skipped_blocked += 1
            continue

        if norm.canonical_key in seen_in_batch:
            skipped_duplicates += 1
            continue

        seen_in_batch.add(norm.canonical_key)

        # Optional field mapping
        name = item.get("name") or item.get("title") or None
        niche = item.get("niche") or item.get("category") or None
        geo = item.get("geo") or item.get("country") or None
        join_url = item.get("join_url") or None
        price_text = item.get("price") or item.get("price_text") or None

        size_raw = item.get("members") or item.get("size") or item.get("size_members")
        size_members = None
        if size_raw is not None:
            try:
                size_members = int(str(size_raw).replace(",", "").strip())
            except ValueError:
                size_members = None

        row = {
            "id": str(uuid4()),
            "canonical_key": norm.canonical_key,
            "canonical_domain": norm.canonical_domain,
            "platform": norm.platform.value if hasattr(norm.platform, "value") else str(norm.platform),
            "platform_id": norm.platform_id,
            "website": norm.website,
            "name": str(name).strip() if name else None,
            "niche": str(niche).strip() if niche else None,
            "geo": str(geo).strip() if geo else None,
            "join_url": str(join_url).strip() if join_url else None,
            "price_text": str(price_text).strip() if price_text else None,
            "size_members": size_members,
            "access_status": "watch",
            "value_score": 20,
            "value_tier": "low",
            "source_queries": json.dumps([args.source]),
            "raw_signals": json.dumps({
                "source": args.source,
                "imported_from": input_file.name,
            }),
        }
        valid_rows.append(row)

    log.info(
        f"Parsed: {len(valid_rows)} new unique records ready to insert. "
        f"Skipped: {skipped_duplicates} duplicates, {skipped_blocked} blocked/junk, {skipped_invalid_url} empty/invalid URLs."
    )

    if not valid_rows:
        log.info("Nothing to insert.")
        return 0

    insert_sql = text(
        """
        INSERT INTO community_scanner (
            id, canonical_key, canonical_domain, platform, platform_id,
            website, name, niche, geo, join_url, price_text, size_members,
            contacts, access_status, value_score, value_tier,
            relevance_score, source_queries, raw_signals, sync_status
        ) VALUES (
            :id, :canonical_key, :canonical_domain, :platform, :platform_id,
            :website, :name, :niche, :geo, :join_url, :price_text, :size_members,
            '{}'::jsonb, :access_status, :value_score, :value_tier,
            0, CAST(:source_queries AS jsonb), CAST(:raw_signals AS jsonb), 'pending'
        )
        ON CONFLICT (canonical_key) DO NOTHING
        """
    )

    total_inserted = 0
    with engine.begin() as conn:
        for i in range(0, len(valid_rows), args.batch_size):
            chunk = valid_rows[i : i + args.batch_size]
            result = conn.execute(insert_sql, chunk)
            inserted = result.rowcount or len(chunk)
            total_inserted += inserted
            log.info(f"Inserted chunk {i // args.batch_size + 1}: {len(chunk)} rows")

    log.info(f"Done! Total inserted into community_scanner: {total_inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
