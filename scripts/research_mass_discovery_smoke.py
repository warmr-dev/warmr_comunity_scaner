"""Smoke-test mass discovery sources (no Discord/Telegram focus).

Read-only probes of public endpoints for research. Does not write to DB.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UA = {
    "User-Agent": (
        "WarmrCommunityScannerResearch/0.1 "
        "(+https://github.com/warmr; research smoke tests)"
    ),
    "Accept": "application/json,text/html,*/*",
}


def fetch(url: str, timeout: float = 25.0) -> tuple[int | None, bytes, str | None]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), None
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return exc.code, body, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, b"", str(exc)[:300]


def probe_commoncrawl(host_pattern: str, limit: int = 50) -> dict[str, Any]:
    # Prefer a recent crawl; fall back across known indexes.
    indexes = (
        "CC-MAIN-2025-43",
        "CC-MAIN-2025-33",
        "CC-MAIN-2025-21",
        "CC-MAIN-2024-51",
        "CC-MAIN-2024-33",
    )
    last_error: str | None = None
    for idx in indexes:
        url = (
            f"https://index.commoncrawl.org/{idx}-index"
            f"?url={host_pattern}&output=json&limit={limit}"
        )
        status, body, err = fetch(url, timeout=40)
        if err and status is None:
            last_error = err
            continue
        if status and status >= 400:
            last_error = f"HTTP {status}: {(err or body[:120].decode('utf-8', 'ignore'))}"
            continue
        lines = [ln for ln in body.decode("utf-8", "ignore").splitlines() if ln.strip()]
        samples: list[str] = []
        for ln in lines[:5]:
            try:
                samples.append(json.loads(ln).get("url", ""))
            except json.JSONDecodeError:
                continue
        return {
            "ok": True,
            "index": idx,
            "status": status,
            "rows": len(lines),
            "sample_urls": samples,
            "url": url,
        }
    return {"ok": False, "error": last_error or "no index responded"}


def probe_circle() -> dict[str, Any]:
    candidates = (
        "https://discover.circle.so/backend/public_api/spaces?page=1&per_page=25",
        "https://discover.circle.so/backend/public_api/communities?page=1&per_page=25",
        "https://discover.circle.so/",
    )
    out: dict[str, Any] = {"endpoints": []}
    for url in candidates:
        status, body, err = fetch(url)
        item: dict[str, Any] = {
            "url": url,
            "status": status,
            "bytes": len(body),
            "error": err,
        }
        text = body.decode("utf-8", "ignore")
        if text.lstrip().startswith("{") or text.lstrip().startswith("["):
            try:
                data = json.loads(text)
                item["json_type"] = type(data).__name__
                if isinstance(data, dict):
                    item["keys"] = list(data.keys())[:12]
                    for key in ("spaces", "communities", "data", "results", "records"):
                        val = data.get(key)
                        if isinstance(val, list):
                            item["list_key"] = key
                            item["count"] = len(val)
                            break
                elif isinstance(data, list):
                    item["count"] = len(data)
            except json.JSONDecodeError:
                item["json"] = False
        else:
            item["html_links"] = len(re.findall(r'href=["\']([^"\']+)["\']', text, re.I))
        out["endpoints"].append(item)
    out["ok"] = any(
        (e.get("status") == 200) and (e.get("count") or e.get("html_links", 0) > 20)
        for e in out["endpoints"]
    )
    return out


def probe_skool() -> dict[str, Any]:
    status, body, err = fetch("https://www.skool.com/discovery")
    if err and status is None:
        return {"ok": False, "error": err}
    text = body.decode("utf-8", "ignore")
    hrefs = re.findall(r'href=["\'](/[^"\']+)["\']', text, re.I)
    bad = {
        "discovery",
        "about",
        "login",
        "signup",
        "pricing",
        "blog",
        "help",
        "api",
        "settings",
        "explore",
        "search",
    }
    slugs: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        path = href.split("?")[0].strip("/")
        if not path or "/" in path:
            continue
        if path.lower() in bad:
            continue
        if not re.fullmatch(r"[a-z0-9-]{3,60}", path, re.I):
            continue
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        slugs.append(path)
    # Also look for absolute community URLs in JSON blobs.
    abs_slugs = re.findall(r"https?://(?:www\.)?skool\.com/([a-z0-9-]{3,60})", text, re.I)
    for s in abs_slugs:
        if s.lower() in bad or s.lower() in seen:
            continue
        seen.add(s.lower())
        slugs.append(s)
    return {
        "ok": status == 200 and len(slugs) > 0,
        "status": status,
        "bytes": len(body),
        "slug_candidates": len(slugs),
        "sample": slugs[:15],
        "error": err,
    }


def probe_reddit() -> dict[str, Any]:
    url = "https://www.reddit.com/subreddits/search.json?q=accounting&limit=25&raw_json=1"
    status, body, err = fetch(url)
    if err and status is None:
        return {"ok": False, "error": err, "url": url}
    try:
        data = json.loads(body.decode("utf-8", "ignore"))
    except json.JSONDecodeError:
        return {
            "ok": False,
            "status": status,
            "error": err or "non-json response",
            "preview": body[:200].decode("utf-8", "ignore"),
            "url": url,
        }
    children = data.get("data", {}).get("children", [])
    names = [c.get("data", {}).get("display_name") for c in children]
    return {
        "ok": status == 200 and len(children) > 0,
        "status": status,
        "count": len(children),
        "sample": names[:10],
        "url": url,
        "error": err,
        "note": "Unauthenticated Reddit often works for light probes; production needs OAuth.",
    }


def probe_hive() -> dict[str, Any]:
    pages = (
        "https://thehiveindex.com/",
        "https://thehiveindex.com/platforms/skool/",
        "https://thehiveindex.com/platforms/circle/",
        "https://thehiveindex.com/platforms/slack/",
        "https://thehiveindex.com/platforms/facebook/",
    )
    out: dict[str, Any] = {"pages": [], "community_pages": 0}
    found: set[str] = set()
    for url in pages:
        status, body, err = fetch(url)
        text = body.decode("utf-8", "ignore")
        community_pages = re.findall(
            r'href=["\'](https?://thehiveindex\.com/communities/[^"\']+|/?communities/[^"\']+)["\']',
            text,
            re.I,
        )
        for href in community_pages:
            found.add(href.split("?")[0].rstrip("/"))
        out["pages"].append(
            {
                "url": url,
                "status": status,
                "bytes": len(body),
                "community_hrefs": len(community_pages),
                "error": err,
            }
        )
    out["community_pages"] = len(found)
    out["sample"] = sorted(found)[:10]
    out["ok"] = any(p.get("status") == 200 for p in out["pages"]) and len(found) > 0
    return out


def probe_forum_finder() -> dict[str, Any]:
    status, body, err = fetch("https://frmie.com/")
    text = body.decode("utf-8", "ignore")
    return {
        "ok": status == 200,
        "status": status,
        "bytes": len(body),
        "mentions_platforms": {
            "reddit": "reddit" in text.lower(),
            "discord": "discord" in text.lower(),
            "slack": "slack" in text.lower(),
            "circle": "circle" in text.lower(),
            "skool": "skool" in text.lower(),
            "facebook": "facebook" in text.lower(),
        },
        "error": err,
        "note": "Interactive search UI; not a bulk dump API.",
    }


def probe_discourse() -> dict[str, Any]:
    forums = (
        "https://meta.discourse.org",
        "https://community.openai.com",
        "https://discuss.huggingface.co",
    )
    out: dict[str, Any] = {"forums": []}
    for base in forums:
        status, body, err = fetch(f"{base}/categories.json")
        item: dict[str, Any] = {"base": base, "status": status, "error": err}
        if status == 200:
            try:
                data = json.loads(body.decode("utf-8", "ignore"))
                cats = data.get("category_list", {}).get("categories", [])
                item["categories"] = len(cats)
                item["sample"] = [c.get("name") for c in cats[:5]]
                item["ok"] = True
            except json.JSONDecodeError:
                item["ok"] = False
                item["preview"] = body[:120].decode("utf-8", "ignore")
        else:
            item["ok"] = False
        out["forums"].append(item)
    out["ok"] = any(f.get("ok") for f in out["forums"])
    out["note"] = (
        "JSON API works per-forum once host is known; discovery of hosts needs "
        "Common Crawl / SERP / seed lists."
    )
    return out


def probe_commoncrawl_patterns() -> dict[str, Any]:
    patterns = {
        "skool": "*.skool.com/*",
        "circle": "*.circle.so/*",
        "facebook_groups": "facebook.com/groups/*",
        "linkedin_groups": "linkedin.com/groups/*",
        "reddit": "reddit.com/r/*",
        "slack_invite": "join.slack.com/t/*",
        "whatsapp": "chat.whatsapp.com/*",
        "discourse_hint": "*/categories.json",
    }
    out: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(probe_commoncrawl, pat, 40): name for name, pat in patterns.items()}
        for fut in as_completed(futs):
            out[futs[fut]] = fut.result()
    return out


def main() -> None:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "no Discord/Telegram primary; maximize raw community candidates",
        "baseline_inventory_claimed": 12000,
        "probes": {},
    }
    probes = {
        "commoncrawl_patterns": probe_commoncrawl_patterns,
        "circle_discovery": probe_circle,
        "skool_discovery": probe_skool,
        "reddit_search": probe_reddit,
        "hive_index": probe_hive,
        "forum_finder": probe_forum_finder,
        "discourse_json": probe_discourse,
    }
    for name, fn in probes.items():
        print(f"probing {name}...", flush=True)
        try:
            report["probes"][name] = fn()
        except Exception as exc:  # noqa: BLE001
            report["probes"][name] = {"ok": False, "error": str(exc)[:300]}

    out_dir = Path(__file__).resolve().parents[1] / "docs"
    out_path = out_dir / "mass-discovery-smoke.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"wrote": str(out_path), "summary": {
        k: (v.get("ok") if isinstance(v, dict) else None)
        for k, v in report["probes"].items()
    }}, indent=2), flush=True)


if __name__ == "__main__":
    main()
