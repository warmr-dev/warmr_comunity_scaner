# warmr_comunity_scaner

Автоматический discovery + enrichment pipeline для professional communities (Warmr inventory).

Документация: [`plan.md`](plan.md) · [`docs/supabase-searxng-setup.md`](docs/supabase-searxng-setup.md)

## Быстрый старт

```bash
docker compose up -d redis searxng
pip install -e ".[dev]"
copy .env.example .env

community-scanner init-db
community-scanner mass-fill --niche harvest --queries 20 --per-query 100 --max-fetch 500
```

## Mass discovery (много комьюнити)

По умолчанию: **Common Crawl + Hive Index** (без Discord/Telegram directory).

```env
DISCOVERY_PROVIDERS=commoncrawl,hive
COMMONCRAWL_INDEX=latest
COMMONCRAWL_MAX_PAGES_PER_PATTERN=30
COMMONCRAWL_PAGE_SIZE=400
HIVE_MAX_DETAIL_PAGES=1200
HIVE_EXCLUDE_DISCORD_TELEGRAM=true
HARVEST_MODE=true
HARVEST_SKIP_ENRICH=true
```

### Railway 24/7 (бесплатные источники → ~100k)

В Variables сервиса:

```env
SCANNER_MODE=mass
DISCOVERY_PROVIDERS=commoncrawl,hive
BUNDLE_SEARXNG=false
HARVEST_MODE=true
HARVEST_SKIP_ENRICH=true
PIPE_QUERIES=80
PIPE_PER_QUERY=100
PIPE_MAX_FETCH=5000
NICHE_LOOPS=0
LOOP_PAUSE_SECONDS=30
COMMONCRAWL_MAX_PAGES_PER_PATTERN=30
COMMONCRAWL_PAGE_SIZE=400
COMMONCRAWL_DELAY_MS=450
HIVE_MAX_DETAIL_PAGES=1200
```

Нужен **volume** на `/app/data` (resumeKey + ротация CC-индексов между циклами). Затем redeploy образа с этим репо.

Опционально добавить свежий SERP:

```env
DISCOVERY_PROVIDERS=commoncrawl,hive,dataforseo
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
```

Сырые URL пишутся в `discovery_results`, затем в `community_scanner`.

```bash
community-scanner mass-fill --queries 40 --per-query 100 --max-fetch 2000
```

Документация: [`docs/mass-discovery-research.md`](docs/mass-discovery-research.md) · [`docs/mass-discovery-implementation-backlog.md`](docs/mass-discovery-implementation-backlog.md)

## Discovery: harvest-first (invite links → filter later)

```env
DISCOVERY_PROVIDERS=commoncrawl,hive
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

`HARVEST_MODE=true` сохраняет invite-shaped URL с минимальным отсевом (только adult). Фильтр ниши/size/языка — позже.

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
| `mass-fill` | Common Crawl + Hive → discovery_results + communities |
| `run` | Discovery + fetch без очереди |
| `discover` | Discovery → Redis queue |
| `worker` | Параллельный fetch из очереди |

## Fetch

`httpx` async GET + BeautifulSoup — не browser, максимально быстро.
