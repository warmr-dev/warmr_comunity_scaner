"""Probe Hive Index topic/platform pages for join URLs."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import httpx

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WarmrHiveProbe/1.0)"}
URLS = [
    "https://thehiveindex.com/topics/entrepreneurship/",
    "https://thehiveindex.com/topics/software-development/",
    "https://thehiveindex.com/platforms/slack/",
    "https://thehiveindex.com/platforms/circle/",
    "https://thehiveindex.com/platforms/facebook-groups/",
    "https://thehiveindex.com/platforms/linkedin/",
    "https://thehiveindex.com/platforms/telegram/",
]


def main() -> None:
    with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
        for url in URLS:
            r = client.get(url)
            print(f"\n{url} status={r.status_code} len={len(r.text)}")
            hrefs = re.findall(r'href="([^"]+)"', r.text)
            abs_links = [urljoin(url, h) for h in hrefs]
            communities = [h for h in abs_links if "/communities/" in h]
            print("community_pages", len(set(communities)), list(sorted(set(communities)))[:5])
            markers = (
                "t.me/",
                "join.slack.com",
                "circle.so",
                "facebook.com/groups",
                "linkedin.com/groups",
                "skool.com",
                "chat.whatsapp.com",
            )
            for m in markers:
                hits = [h for h in abs_links if m in h.lower()]
                if hits:
                    print(m, len(set(hits)), hits[:3])
            if communities:
                detail = client.get(sorted(set(communities))[0])
                print("detail", detail.url, detail.status_code)
                ext = re.findall(r'href="(https?://[^"]+)"', detail.text)
                useful = [
                    e
                    for e in ext
                    if any(
                        x in e.lower()
                        for x in (
                            "t.me",
                            "slack",
                            "circle.so",
                            "facebook.com/groups",
                            "linkedin.com/groups",
                            "skool",
                            "whatsapp",
                            "discord",
                        )
                    )
                ]
                print("detail_external", useful[:10])


if __name__ == "__main__":
    main()
