# ~~Production setup: SearXNG + Redis queue + Supabase~~ (deprecated)

> **Deprecated.** SearXNG removed from the runtime. Use [`supabase-brave-setup.md`](supabase-brave-setup.md).

# Production setup: SearXNG + Redis queue + Supabase

## Services on Railway

| Service | Purpose |
|---------|---------|
| `warmr_comunity_scaner` | Scanner cron (discovery + fetch worker) |
| `searxng` | Global web search (`DISCOVERY_PROVIDERS=searxng`) |
| `redis` | Fetch queue for large batches |
| Supabase | Postgres `community_scanner` table |

Optional: **2–3 replicas** of scanner with `SCANNER_MODE=worker` to scale fetch linearly.

## 1. Supabase

```env
DATABASE_URL=postgresql+psycopg://postgres.bpxiawuzidhjalaemejy:PASSWORD@aws-0-eu-west-2.pooler.supabase.com:5432/postgres
```

## 2. SearXNG (global search)

```env
DISCOVERY_PROVIDERS=searxng
SEARXNG_BASE_URL=http://<searxng-service>.railway.internal:8080
DISCOVERY_CONCURRENCY=10
PIPE_QUERIES=20
PIPE_PER_QUERY=30
```

No seeds — discovery is 100% SearXNG web search scoped to **USA** (`PIPE_GEO=USA`, `SEARXNG_LANGUAGE=en-US`).

## 3. Redis queue

```env
REDIS_URL=redis://...
USE_FETCH_QUEUE=true
SCANNER_MODE=full
```

## 4. Speed tuning

```env
FETCH_CONCURRENCY=100        # async HTTP, connection pool
CRAWL_DOWNLOAD_DELAY_SECONDS=0
HTTP_TIMEOUT_SECONDS=12
FETCH_BATCH_SIZE=1000
WORKER_MAX_ITEMS=500000
```

**Throughput** (async fetch, ~1.5s avg per site):

| Sites | 1 worker @ 100 concurrency | 3 worker replicas |
|-------|---------------------------|-------------------|
| 100k | ~25 min | ~8 min |
| 500k | ~2 h | ~40 min |
| 1M | ~4 h | ~1.3 h |

Previous ~14h was with concurrency=20 + 0.5s delay + sync threads.

## 5. Cron 2×/day

- `06:00 UTC` — `SCANNER_MODE=full` (discovery fills queue, worker drains)
- `18:00 UTC` — same

Or split:
- Cron discovery only (`SCANNER_MODE=discovery`)
- Always-on workers (`SCANNER_MODE=worker`, `WORKER_MAX_ITEMS=1000000`)

## 6. Fetch method

HTTPS GET + BeautifulSoup (no browser). Fast; JS-heavy sites may need Playwright later.

## 7. Minimal prod env

```env
DISCOVERY_PROVIDERS=searxng
SEARXNG_BASE_URL=http://searxng:8080
REDIS_URL=redis://...
USE_FETCH_QUEUE=true
FETCH_CONCURRENCY=100
WORKER_MAX_ITEMS=500000
CRAWL_DOWNLOAD_DELAY_SECONDS=0
```
