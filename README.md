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

## Discovery: harvest-first (invite links → filter later)

```env
DISCOVERY_PROVIDERS=directory,searxng
HARVEST_MODE=true
HARVEST_SKIP_ENRICH=true
SEARXNG_BASE_URL=http://127.0.0.1:8080
SEARXNG_LANGUAGE=en-US
DISCOVERY_CONCURRENCY=1
CRAWL_DOWNLOAD_DELAY_SECONDS=0.6
DIRECTORY_MAX_CHANNELS_PER_SITE=40
PIPE_NICHE=harvest
PIPE_GEO=USA
PIPE_QUERIES=40
PIPE_PER_QUERY=25
```

`HARVEST_MODE=true` ищет широкие invite-запросы (`inurl:t.me/+`, `discord.gg`, …) и сохраняет invite-shaped URL с минимальным отсевом (только adult). Фильтр ниши/size/языка — позже.

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
