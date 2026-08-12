# warmr_comunity_scaner

Автоматический discovery + enrichment pipeline для professional communities (Warmr inventory).

Документация: [`plan.md`](plan.md) · [`docs/supabase-brave-setup.md`](docs/supabase-brave-setup.md)

## Быстрый старт

```bash
pip install -e ".[dev]"
copy .env.example .env
# set BRAVE_SEARCH_API_KEY in .env

community-scanner init-db
community-scanner run --niche business --queries 5 --per-query 10 --max-fetch 20
```

## Discovery: Brave Search

```env
DISCOVERY_PROVIDERS=brave
BRAVE_SEARCH_API_KEY=your_key_here
BRAVE_COUNTRY=us
BRAVE_SEARCH_LANG=en
BRAVE_MAX_REQUESTS=200
PIPE_NICHE=business
PIPE_GEO=USA
PIPE_QUERIES=20
PIPE_PER_QUERY=25
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
| `discover` | Brave search → Redis queue |
| `worker` | Параллельный fetch из очереди |
| `run` | Discovery + fetch без очереди |

## Fetch

`httpx` async GET + BeautifulSoup — не browser, максимально быстро.
