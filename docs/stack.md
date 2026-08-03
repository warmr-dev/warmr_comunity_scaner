# Stack

## Выбор (зафиксировано)

| Слой | Технология | Почему |
|------|------------|--------|
| Language | **Python 3.12+** | Лучшая экосистема Scrapy/Playwright, быстрый delivery |
| Discovery primary | **Directories/seeds + Brave Search API** | Высокий signal + стабильный официальный search API |
| Discovery overflow/dev | **SearXNG** (Docker) | Дешёвый bulk/local; не single point of failure |
| HTTP crawl | **Scrapy** | Масштаб, pipelines, concurrency, middleware |
| JS render | **Playwright** (+ scrapy-playwright) | Только для JS-heavy страниц |
| DB | **PostgreSQL 16** | Source of truth, дедуп, incremental, интеграция |
| ORM / SQL | **SQLAlchemy 2** + Alembic | Миграции, типизированные модели |
| Queue / workers | **Redis** + **ARQ** или Celery | Weekly jobs, ретраи, параллель по батчам |
| Scheduler | Cron / Celery Beat / ARQ cron | Регулярные прогоны |
| Config | `.env` + pydantic-settings | Секреты и параметры окружения |
| Containers | **Docker Compose** | SearXNG + Postgres + Redis + worker |
| Export | gspread / Airtable API | Витрины, не primary storage |
| Optional LLM | OpenAI-compatible API | Niche/audience/value на сложных страницах |

## Пакеты (ориентир)

```text
scrapy
scrapy-playwright
playwright
httpx
sqlalchemy
alembic
psycopg[binary]
redis
arq          # или celery + redis
pydantic
pydantic-settings
python-dotenv
tenacity
beautifulsoup4
lxml
gspread      # optional export
pyairtable   # optional export
```

## Что сознательно не берём в основу

| Вариант | Причина |
|---------|---------|
| Google CSE как foundation | Закрыт для новых, sunset 2027 |
| SearXNG как единственный discovery | Bans/CAPTCHA, нестабильное качество на объёме; см. risks-and-strategy.md |
| Playwright на 100% трафика | Дорого на сотнях тысяч URL |
| Sheets/Airtable как единственная БД | Не выдержит путь к 1M |
| Публичные SearXNG инстансы в проде | JSON часто выключен, rate-limit, нестабильность |
| Selenium | Playwright достаточно и обычно удобнее |

## Окружения

- `local` — docker compose, небольшой smoke-run
- `staging` — полный pipeline на ограниченном наборе ниш/гео
- `prod` — weekly (или чаще) incremental sync в экосистему Warmr

## Минимальный Compose

Сервисы:

1. `searxng`
2. `postgres`
3. `redis`
4. `worker` (discovery + crawl + classify)
5. `scheduler` (опционально отдельным процессом)

Приложение читает только:

- SearXNG HTTP API
- публичные сайты кандидатов
- Postgres / Redis
- export API (по флагу)

Никакого прямого HTML-скрейпинга Google Search results pages.
