"""Inspect a few Hive Index community detail pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarmrHiveProbe/1.0)"}


def main() -> None:
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        topic = client.get("https://thehiveindex.com/topics/entrepreneurship/")
        pages = sorted(
            {
                urljoin(str(topic.url), h)
                for h in re.findall(r'href="([^"]+)"', topic.text)
                if "/communities/" in h and h.rstrip("/").count("/") >= 2
            }
        )[:8]
        print("sample pages", pages)
        for page in pages:
            r = client.get(page)
            hrefs = re.findall(r'href="(https?://[^"]+)"', r.text)
            useful = [
                h
                for h in hrefs
                if any(
                    x in h.lower()
                    for x in (
                        "t.me",
                        "join.slack",
                        "slack.com",
                        "circle.so",
                        "facebook.com/groups",
                        "linkedin.com/groups",
                        "skool.com",
                        "chat.whatsapp",
                        "discord",
                    )
                )
                and "thehiveindex.com" not in h.lower()
            ]
            # Also look for data attributes / plain text URLs
            text_urls = re.findall(
                r"https?://(?:join\.slack\.com|t\.me|www\.facebook\.com/groups|www\.linkedin\.com/groups|[\w-]+\.circle\.so|www\.skool\.com|chat\.whatsapp\.com)[^\s\"'<>]+",
                r.text,
                re.I,
            )
            print(page, "href", useful[:5], "text", text_urls[:5])

        platforms = client.get("https://thehiveindex.com/")
        plat = sorted(
            {
                urljoin("https://thehiveindex.com/", h)
                for h in re.findall(r'href="([^"]+)"', platforms.text)
                if "/platforms/" in h
            }
        )
        print("platforms", plat)


if __name__ == "__main__":
    main()
