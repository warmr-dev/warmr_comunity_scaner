"""Debug Skool discovery HTML variants."""

from __future__ import annotations

from pathlib import Path

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def main() -> None:
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        r = client.get("https://www.skool.com/discovery")
        Path("data/skool_last.html").write_text(r.text, encoding="utf-8")
        print("status", r.status_code, "len", len(r.text), "url", r.url)
        print("has_next", "__NEXT_DATA__" in r.text)
        print("has_challenge", "challenge" in r.text.lower() or "cf-ray" in r.text.lower())
        print(r.text[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
