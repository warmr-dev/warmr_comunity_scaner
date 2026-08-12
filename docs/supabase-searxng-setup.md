# Production setup: SearXNG + Supabase (`community_scanner`)

Project ref: `bpxiawuzidhjalaemejy` (name: scanner)

## Services

| Piece | Role |
|-------|------|
| Railway scanner image | Bundled SearXNG + pipeline (`BUNDLE_SEARXNG=true`) |
| Supabase | Postgres `community_scanner` |
| Redis (optional) | Fetch queue for large batches (`USE_FETCH_QUEUE=true`) |

## Core env

```env
DISCOVERY_PROVIDERS=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_LANGUAGE=en-US
BUNDLE_SEARXNG=true
DISCOVERY_CONCURRENCY=1
CRAWL_DOWNLOAD_DELAY_SECONDS=0.6

PIPE_GEO=USA
PIPE_NICHES=software-engineering,education
PIPE_QUERIES=50
PIPE_PER_QUERY=25
PIPE_MAX_FETCH=200
NICHE_LOOPS=20
SCANNER_MODE=run
```

## High volume (many invites)

1. Keep `DISCOVERY_CONCURRENCY=1` and delay ≥0.5s — Bing bans faster bursts from Railway IPs.
2. Raise volume via **more niches + NICHE_LOOPS**, not concurrency.
3. For 100k–1M **fetch**, split:
   - discovery cron (`SCANNER_MODE=discovery` / `run`)
   - Redis + 2–3 workers (`USE_FETCH_QUEUE=true`, `SCANNER_MODE=worker`, `FETCH_CONCURRENCY=100`)

## Speed tuning (fetch)

```env
FETCH_CONCURRENCY=100
HTTP_TIMEOUT_SECONDS=10
FETCH_BATCH_SIZE=1000
WORKER_MAX_ITEMS=1000000
```

| Sites | 1 worker @ 100 concurrency | 3 workers |
|-------|----------------------------|-----------|
| 100k | ~25 min | ~8 min |
| 1M | ~4 h | ~1.3 h |

## DB

```env
DATABASE_URL=postgresql+psycopg://postgres.bpxiawuzidhjalaemejy:PASSWORD@aws-0-eu-west-2.pooler.supabase.com:5432/postgres
```

Use Supabase **Session pooler** (IPv4), not direct `db.*.supabase.co`.
