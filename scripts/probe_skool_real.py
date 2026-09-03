"""Extract real Skool community slugs from public discovery pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_slugs(html: str) -> set[str]:
    slugs: set[str] = set()
    for m in re.finditer(r"skool\.com/([a-z0-9][a-z0-9_-]{1,40})", html, re.I):
        slugs.add(m.group(1).lower())
    for m in re.finditer(r'"slug"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', html, re.I):
        slugs.add(m.group(1).lower())
    for m in re.finditer(r'"name"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', html, re.I):
        # many group names are also route names
        if "/" not in m.group(1):
            slugs.add(m.group(1).lower())
    start = html.find('id="__NEXT_DATA__"')
    if start >= 0:
        gt = html.find(">", start)
        end = html.find("</script>", gt)
        try:
            data = json.loads(html[gt + 1 : end])
            blob = json.dumps(data)
            for m in re.finditer(r'"slug"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', blob, re.I):
                slugs.add(m.group(1).lower())
            for m in re.finditer(r'"name"\s*:\s*"([a-z0-9][a-z0-9_-]{1,40})"', blob, re.I):
                slugs.add(m.group(1).lower())
        except Exception:
            pass
    blocked = {
        "discovery",
        "about",
        "login",
        "signup",
        "pricing",
        "help",
        "blog",
        "www",
        "api",
        "settings",
        "admin",
        "skool",
    }
    return {s for s in slugs if s not in blocked and not s.startswith("-")}


def main() -> None:
    urls = [
        "https://www.skool.com/discovery",
        "https://www.skool.com/discovery?c=f8ff1eeabd1d4e8ef1a1c19c4e4c4d4a",
        "https://www.skool.com/discovery?q=ai",
        "https://www.skool.com/discovery?q=marketing",
        "https://www.skool.com/discovery?q=fitness",
        "https://www.skool.com/discovery?q=business",
        "https://www.skool.com/discovery?q=crypto",
        "https://www.skool.com/discovery?q=real+estate",
        "https://www.skool.com/discovery?q=coaching",
        "https://www.skool.com/discovery?q=agency",
    ]
    all_slugs: set[str] = set()
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        for url in urls:
            r = client.get(url)
            slugs = extract_slugs(r.text)
            print(f"{url} status={r.status_code} slugs={len(slugs)} next={'__NEXT_DATA__' in r.text}")
            all_slugs |= slugs
    Path("data/skool_real_slugs.txt").write_text("\n".join(sorted(all_slugs)), encoding="utf-8")
    print("total_unique", len(all_slugs))
    print(sorted(all_slugs)[:40])


if __name__ == "__main__":
    main()
