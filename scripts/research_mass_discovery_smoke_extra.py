"""Additional smoke probes that PowerShell inline Python cannot escape well."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
}


def get(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b"", str(exc)[:200]
    except Exception as exc:  # noqa: BLE001
        return None, b"", str(exc)[:200]


def main() -> None:
    out: dict = {}

    st, body, err = get("https://old.reddit.com/subreddits/search.json?q=accounting&limit=25")
    item = {"status": st, "error": err, "bytes": len(body)}
    if st == 200:
        try:
            data = json.loads(body)
            kids = data.get("data", {}).get("children", [])
            item["count"] = len(kids)
            item["sample"] = [c["data"].get("display_name") for c in kids[:8]]
            item["ok"] = len(kids) > 0
        except json.JSONDecodeError:
            item["ok"] = False
            item["preview"] = body[:200].decode("utf-8", "ignore")
    else:
        item["ok"] = False
        item["preview"] = body[:200].decode("utf-8", "ignore")
    out["old_reddit"] = item

    st, body, err = get("https://www.skool.com/discovery?c=business&o=0")
    text = body.decode("utf-8", "ignore")
    out["skool_biz"] = {
        "status": st,
        "error": err,
        "bytes": len(body),
        "slug_like": len(re.findall(r"skool\\.com/[a-z0-9-]{3,}", text, re.I)),
        "ok": st == 200 and "skool" in text.lower(),
        "preview": text[:180].replace("\n", " "),
    }

    st, body, err = get("https://discover.circle.so/")
    text = body.decode("utf-8", "ignore")
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, re.I)
    api_urls = list(dict.fromkeys(re.findall(r"https?://[^\"']*public_api[^\"']*", text)))[:10]
    backend = list(dict.fromkeys(re.findall(r"/backend/[^\"']+", text)))[:15]
    out["circle_home"] = {
        "status": st,
        "bytes": len(body),
        "hrefs": len(hrefs),
        "sample_hrefs": hrefs[:20],
        "api_urls": api_urls,
        "backend_paths": backend,
        "ok": st == 200,
    }

    st, body, err = get("https://index.commoncrawl.org/collinfo.json", timeout=45)
    item = {"status": st, "error": err, "bytes": len(body)}
    collinfo: list = []
    if st == 200:
        collinfo = json.loads(body)
        item["indexes"] = len(collinfo)
        item["latest"] = [
            (x.get("id"), x.get("cdx-api") or x.get("name")) for x in collinfo[:5]
        ]
        item["ok"] = True
    else:
        item["ok"] = False
    out["cc_collinfo"] = item

    # Try one recent index from collinfo if available
    if collinfo:
        cdx = collinfo[0].get("cdx-api")
        if cdx:
            test = f"{cdx}?url=*.skool.com/*&output=json&limit=10"
            st2, body2, err2 = get(test, timeout=60)
            lines = [ln for ln in body2.decode("utf-8", "ignore").splitlines() if ln.strip()]
            samples = []
            for ln in lines[:5]:
                try:
                    samples.append(json.loads(ln).get("url"))
                except json.JSONDecodeError:
                    pass
            out["cc_skool_via_collinfo"] = {
                "url": test,
                "status": st2,
                "error": err2,
                "rows": len(lines),
                "sample": samples,
                "ok": st2 == 200 and len(lines) > 0,
            }

    st, body, err = get("https://thehiveindex.com/communities/1-percent-ecom-club/")
    text = body.decode("utf-8", "ignore")
    invites = re.findall(
        r"https?://(?:join\.slack\.com|www\.skool\.com|chat\.whatsapp\.com|"
        r"www\.facebook\.com/groups|www\.linkedin\.com/groups|t\.me)[^\s\"']+",
        text,
        re.I,
    )
    out["hive_detail"] = {
        "status": st,
        "bytes": len(body),
        "invite_like": len(invites),
        "sample": invites[:8],
        "ok": st == 200,
    }

    path = Path(__file__).resolve().parents[1] / "docs" / "mass-discovery-smoke-extra.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"wrote": str(path), "ok": {k: v.get("ok") for k, v in out.items()}}, indent=2))


if __name__ == "__main__":
    main()
