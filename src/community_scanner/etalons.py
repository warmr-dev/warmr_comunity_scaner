from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ETALONS_PATH = ROOT / "data" / "warmr_gold_etalons.json"


@lru_cache
def load_gold_etalons() -> list[dict]:
    if not ETALONS_PATH.exists():
        return []
    return json.loads(ETALONS_PATH.read_text(encoding="utf-8"))


def etalon_seed_entries() -> list[dict]:
    """Convert Warmr gold etalons into seeds.json-compatible rows."""
    rows: list[dict] = []
    for item in load_gold_etalons():
        urls = list(item.get("public_urls") or [])
        if item.get("join_link") and item["join_link"] not in urls:
            if "slack.com/" not in item["join_link"].rstrip("/") + "/" or item["join_link"].count(".") >= 2:
                # skip bare https://slack.com
                if item["join_link"].rstrip("/") not in {"https://slack.com", "http://slack.com"}:
                    urls.insert(0, item["join_link"])
        tags = (
            f"warmr-gold etalon {item.get('name')} {item.get('slug')} "
            f"{item.get('platform')} founders paid community"
        )
        for url in urls:
            rows.append(
                {
                    "url": url,
                    "title": f"{item['name']} (Warmr gold)",
                    "tags": tags,
                }
            )
    return rows


def match_etalon(name: str | None, website: str | None, platform_id: str | None) -> dict | None:
    blob = " ".join(
        x.lower() for x in [name or "", website or "", platform_id or ""] if x
    )
    for item in load_gold_etalons():
        needles = [
            (item.get("name") or "").lower(),
            (item.get("slug") or "").lower(),
        ]
        for url in item.get("public_urls") or []:
            needles.append(url.lower())
        if item.get("join_link"):
            needles.append(item["join_link"].lower())
        for needle in needles:
            if needle and needle in blob:
                return item
            # also match slug token in domain (joinhampton.slack.com)
            if needle and needle.replace(" ", "") in blob.replace(" ", ""):
                return item
    return None
