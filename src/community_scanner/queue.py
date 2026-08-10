from __future__ import annotations

import json
from typing import Any

import redis

from community_scanner.config import Settings


def get_redis(settings: Settings) -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_fetch_jobs(settings: Settings, jobs: list[dict[str, Any]]) -> int:
    if not jobs:
        return 0
    client = get_redis(settings)
    payload = [json.dumps(job, ensure_ascii=False) for job in jobs]
    client.lpush(settings.fetch_queue_key, *payload)
    return len(jobs)


def dequeue_fetch_jobs(settings: Settings, count: int) -> list[dict[str, Any]]:
    client = get_redis(settings)
    jobs: list[dict[str, Any]] = []
    for _ in range(count):
        raw = client.rpop(settings.fetch_queue_key)
        if raw is None:
            break
        jobs.append(json.loads(raw))
    return jobs


def queue_length(settings: Settings) -> int:
    client = get_redis(settings)
    return int(client.llen(settings.fetch_queue_key))


def fetch_job_from_candidate(hit, norm, *, geo: str = "USA") -> dict[str, Any]:
    return {
        "url": hit.url,
        "title": hit.title,
        "query": hit.query,
        "website": norm.website,
        "canonical_key": norm.canonical_key,
        "canonical_domain": norm.canonical_domain,
        "platform": norm.platform.value,
        "platform_id": norm.platform_id,
        "geo": geo,
    }
