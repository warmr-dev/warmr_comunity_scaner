"""Volume estimate probes against Common Crawl CDX (latest index)."""

from __future__ import annotations

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

INDEX = "https://index.commoncrawl.org/CC-MAIN-2026-34-index"
UA = {"User-Agent": "WarmrCommunityScannerResearch/0.1"}


def cdx(url_pattern: str, limit: int = 200) -> dict:
    api = f"{INDEX}?url={url_pattern}&output=json&limit={limit}"
    req = urllib.request.Request(api, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", "ignore")
            status = resp.status
    except Exception as exc:  # noqa: BLE001
        return {"pattern": url_pattern, "ok": False, "error": str(exc)[:200]}

    rows = []
    for ln in body.splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue

    urls = [r.get("url", "") for r in rows]
    # Derive community-like keys
    keys: set[str] = set()
    for u in urls:
        p = urlparse(u)
        host = p.netloc.lower().removeprefix("www.")
        parts = [x for x in p.path.split("/") if x]
        if host.endswith("skool.com") and parts:
            slug = parts[0].lower()
            if slug not in {"discovery", "about", "login", "signup", "pricing"}:
                keys.add(f"skool:{slug}")
        elif host.endswith("circle.so") and parts:
            keys.add(f"circle:{parts[0].lower()}")
        elif "facebook.com" in host and len(parts) >= 2 and parts[0] == "groups":
            keys.add(f"facebook:{parts[1].lower()}")
        elif "linkedin.com" in host and len(parts) >= 2 and parts[0] == "groups":
            keys.add(f"linkedin:{parts[1].lower()}")
        elif "reddit.com" in host and len(parts) >= 2 and parts[0] == "r":
            keys.add(f"reddit:{parts[1].lower()}")
        elif host == "join.slack.com" and len(parts) >= 2 and parts[0] == "t":
            keys.add(f"slack:{parts[1].lower()}")
        elif host == "chat.whatsapp.com" and parts:
            keys.add(f"whatsapp:{parts[0]}")
        elif parts and parts[-1] == "categories.json":
            keys.add(f"discourse_host:{host}")
        else:
            keys.add(f"url:{host}{p.path.lower().rstrip('/')}")

    return {
        "pattern": url_pattern,
        "ok": True,
        "status": status,
        "rows_returned": len(rows),
        "unique_keys_in_sample": len(keys),
        "hit_limit": len(rows) >= limit,
        "sample_keys": sorted(keys)[:12],
        "sample_urls": urls[:5],
    }


def main() -> None:
    patterns = {
        "skool": "*.skool.com/*",
        "circle": "*.circle.so/*",
        "facebook_groups": "facebook.com/groups/*",
        "linkedin_groups": "linkedin.com/groups/*",
        "reddit": "reddit.com/r/*",
        "slack_invite": "join.slack.com/t/*",
        "whatsapp": "chat.whatsapp.com/*",
        "discourse_categories_json": "*/categories.json",
        "mighty": "*.mightynetworks.com/*",
        "geneva": "*.geneva.com/*",
    }
    out = {"index": INDEX, "limit_per_pattern": 200, "patterns": {}}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(cdx, pat, 200): name for name, pat in patterns.items()}
        for fut in as_completed(futs):
            name = futs[fut]
            out["patterns"][name] = fut.result()
            print(name, out["patterns"][name].get("ok"), out["patterns"][name].get("rows_returned"), flush=True)

    path = Path(__file__).resolve().parents[1] / "docs" / "mass-discovery-cc-volume.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", path)


if __name__ == "__main__":
    main()
