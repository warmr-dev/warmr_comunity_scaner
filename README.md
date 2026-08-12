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

## Discovery: SearXNG (бесплатный web search через Bing)

```env
DISCOVERY_PROVIDERS=searxng
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_LANGUAGE=en-US
DISCOVERY_CONCURRENCY=1
CRAWL_DOWNLOAD_DELAY_SECONDS=0.6
PIPE_NICHE=business
PIPE_GEO=USA
PIPE_QUERIES=50
PIPE_PER_QUERY=25
```

На Railway образ бандлит SearXNG (`BUNDLE_SEARXNG=true`) — отдельный сервис не обязателен.

## Скорость fetch

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

Для 1M за ~1.5 ч: **3 worker-реплики** + Redis (`USE_FETCH_QUEUE=true`, `SCANNER_MODE=worker`).

## Команды

| Команда | Назначение |
|---------|------------|
| `discover` | SearXNG search → Redis queue |
| `worker` | Параллельный fetch из очереди |
| `run` | Discovery + fetch без очереди |

## Fetch

`httpx` async GET + BeautifulSoup — не browser, максимально быстро.
