"""Test DDG and Brave invite discovery quickly."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from community_scanner.config import get_settings  # noqa: E402
from community_scanner.discovery.ddg import DuckDuckGoProvider  # noqa: E402
from community_scanner.invites import classify_invite_url, find_all_invites_in_text  # noqa: E402


def summarize(name: str, hits) -> None:
    invites = 0
    for h in hits:
        blob = " ".join(filter(None, [h.url, h.title, h.snippet]))
        found = find_all_invites_in_text(blob)
        direct = classify_invite_url(h.url or "")
        if direct and all(i.url != direct.url for i in found):
            found = [direct, *found]
        invites += len(found)
        print(f"{name}\t{h.url[:140]}\tinv={len(found)}")
    print(f"{name}_SUMMARY hits={len(hits)} invites={invites}")


def main() -> None:
    settings = get_settings()
    ddg = DuckDuckGoProvider()
    for q in [
        "inurl:chat.whatsapp.com",
        'site:skool.com "members"',
        "inurl:join.slack.com/t/",
    ]:
        try:
            hits = ddg.search(q, count=10)
            summarize(f"ddg:{q[:30]}", hits)
        except Exception as exc:  # noqa: BLE001
            print("ddg_error", q, type(exc).__name__, exc)

    if settings.brave_search_api_key:
        try:
            from community_scanner.discovery.brave import BraveSearchProvider

            brave = BraveSearchProvider(api_key=settings.brave_search_api_key)
            hits = brave.search("chat.whatsapp.com invite", count=10)
            summarize("brave", hits)
        except Exception as exc:  # noqa: BLE001
            print("brave_error", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
