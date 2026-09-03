"""Quick Bing invite URL sample for WhatsApp/Slack/Skool."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.discovery.bing import BingHtmlProvider  # noqa: E402
from community_scanner.invites import classify_invite_url, find_all_invites_in_text  # noqa: E402


def main() -> None:
    bing = BingHtmlProvider(delay=0.8)
    queries = [
        "inurl:chat.whatsapp.com",
        "inurl:join.slack.com/t/",
        "site:skool.com -discovery -about",
        'site:github.com "chat.whatsapp.com"',
        'site:github.com "join.slack.com/t/"',
    ]
    for q in queries:
        hits = bing.search(q, count=20)
        invites = 0
        for h in hits:
            blob = " ".join(filter(None, [h.url, h.title, h.snippet]))
            found = find_all_invites_in_text(blob) or ([classify_invite_url(h.url)] if classify_invite_url(h.url) else [])
            found = [x for x in found if x]
            invites += len(found)
            print(f"HIT\t{q[:40]}\t{h.url[:120]}\tinvites={len(found)}")
        print(f"SUMMARY q={q!r} hits={len(hits)} invites={invites}")


if __name__ == "__main__":
    main()
