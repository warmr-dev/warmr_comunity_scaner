from __future__ import annotations

import json

from community_scanner.discovery.base import DiscoveryProvider
from community_scanner.etalons import etalon_seed_entries
from community_scanner.models import DiscoveryHit
from community_scanner.paths import data_dir

SEEDS_PATH = data_dir() / "seeds.json"

# Fallback if seeds.json missing
DEFAULT_SEEDS: list[tuple[str, str, str]] = [
    ("https://www.skool.com/discovery", "Skool Discovery", "community skool business"),
    ("https://www.indiehackers.com/", "Indie Hackers", "entrepreneur community founders"),
    ("https://www.flicpa.org/", "Florida Institute of CPAs", "florida accounting CPA community"),
]


def load_seeds() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    # Warmr gold etalons first
    for item in etalon_seed_entries():
        url = item["url"]
        if url in seen:
            continue
        seen.add(url)
        rows.append((url, item.get("title") or url, item.get("tags") or "warmr-gold"))

    if SEEDS_PATH.exists():
        raw = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
        for item in raw:
            url = item["url"]
            if url in seen:
                continue
            seen.add(url)
            rows.append((url, item.get("title") or url, item.get("tags") or ""))
        return rows
    if rows:
        return rows
    return DEFAULT_SEEDS


class SeedsProvider(DiscoveryProvider):
    name = "seeds"

    def __init__(self, seeds: list[tuple[str, str, str]] | None = None) -> None:
        self.seeds = seeds or load_seeds()

    def search(self, query: str, count: int = 10) -> list[DiscoveryHit]:
        q_tokens = [t for t in query.lower().split() if len(t) > 2]
        scored: list[tuple[int, tuple[str, str, str]]] = []

        for seed in self.seeds:
            url, title, tag = seed
            blob = f"{title} {tag} {url}".lower()
            score = sum(1 for t in q_tokens if t in blob)
            scored.append((score, seed))

        scored.sort(key=lambda x: (-x[0], x[1][1]))
        # Prefer matches; if weak match, still return top of list so runs stay useful
        chosen = [s for sc, s in scored if sc > 0][:count]
        if len(chosen) < count:
            for _, seed in scored:
                if seed not in chosen:
                    chosen.append(seed)
                if len(chosen) >= count:
                    break

        return [
            DiscoveryHit(url=url, title=title, snippet=tag, provider=self.name, query=query)
            for url, title, tag in chosen
        ]
