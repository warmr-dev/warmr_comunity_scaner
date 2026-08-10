# warmr_comunity_scaner

Автоматический discovery + enrichment pipeline для professional communities (Warmr inventory).

Документация: [`plan.md`](plan.md) · [`docs/supabase-searxng-setup.md`](docs/supabase-searxng-setup.md)

## Быстрый старт

```bash
docker compose up -d redis searxng
pip install -e ".[dev]"
copy .env.example .env

community-scanner init-db
community-scanner run --niche business --queries 5 --per-query 10 --max-fetch 20
```

## Discovery: только SearXNG (глобальный поиск)

```env
DISCOVERY_PROVIDERS=searxng
SEARXNG_BASE_URL=http://localhost:8080
PIPE_NICHE=business
PIPE_GEO=USA
SEARXNG_LANGUAGE=en-US
PIPE_QUERIES=20
PIPE_PER_QUERY=30
```

## Скорость fetch

Async HTTP + connection pool. Ключевые переменные:

```env
FETCH_CONCURRENCY=100
CRAWL_DOWNLOAD_DELAY_SECONDS=0
HTTP_TIMEOUT_SECONDS=12
FETCH_BATCH_SIZE=1000
```

| Объём | ~время (100 concurrent) |
|-------|-------------------------|
| 100k | 25 мин |
| 500k | 2 ч |
| 1M | 4 ч |

Для 1M за ~1.5 ч: **3 worker-реплики** на Railway (`SCANNER_MODE=worker`).

## Команды

| Команда | Назначение |
|---------|------------|
| `discover` | SearXNG search → Redis queue |
| `worker` | Параллельный fetch из очереди |
| `run` | Discovery + fetch без очереди |

## Fetch

`httpx` async GET + BeautifulSoup — не browser, максимально быстро.
