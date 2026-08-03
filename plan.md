# Warmr Community Scanner — Plan

Система автоматического поиска и сбора **ценных professional communities** для пополнения inventory Warmr.

> Vendors платят за лиды. Боты мониторят комьюнити и ловят intent-посты.  
> Этот тул нужен, чтобы **находить больше качественных комьюнити** (сейчас ~20k ценных из ~80k; цель — порядка 1M хороших).

## Что делает система

1. Генерирует сотни поисковых запросов (гео, ниша, аудитория, тип).
2. Делает discovery через **SearXNG API** (не через массовый скрейпинг Google SERP).
3. Парсит публичные страницы найденных сообществ (**Scrapy + Playwright fallback**).
4. Собирает: название, сайт, нишу, аудиторию, join-ссылку, цену, размер, контакты.
5. Удаляет дубли и нерелевантное.
6. Классифицирует: **Join / Apply / Watch / Reject** + **value_tier** (ценность для лидов).
7. Пишет в **Postgres**, выгружает в Sheets/Airtable, синкает new/changed в экосистему Warmr.
8. Запускается регулярно.

## Ключевое ограничение

Не строить решение на прямом массовом скрейпинге Google.  
Поиск — discovery через API/SearXNG; основной парсинг — по публичным сайтам сообществ.

## Зафиксированный стек (кратко)

| Слой | Выбор |
|------|--------|
| Language | Python 3.10+ (лучше 3.12+) |
| Discovery primary | Directories/seeds + **Brave Search API** |
| Discovery secondary / cheap | SearXNG (overflow/dev), платный SERP API при необходимости |
| Crawl | Scrapy + Playwright (точечно) |
| DB | PostgreSQL (сканер) → sync в Warmr DB после обработки |
| Runtime | **Docker** на **Railway / Render** (не Edge, VPS не обязателен) |
| Jobs | Redis + ARQ/Celery |
| Deploy | Docker Compose |

> Важно: путь «только SearXNG → весь интернет» **не** самый оптимальный для цели 1M ценных.  
> См. [docs/risks-and-strategy.md](docs/risks-and-strategy.md).

Подробности: [docs/stack.md](docs/stack.md)

## Документация

| Документ | Содержание |
|----------|------------|
| [docs/research.md](docs/research.md) | Ресерч, продуктовый контекст, решения |
| [docs/risks-and-strategy.md](docs/risks-and-strategy.md) | Риски, альтернативы, revised стратегия |
| [docs/hosting.md](docs/hosting.md) | Docker vs Edge, частота прогонов, куда деплоить |
| [docs/stack.md](docs/stack.md) | Стек и зависимости |
| [docs/architecture.md](docs/architecture.md) | Архитектура, схема данных, классификация |
| [docs/integration.md](docs/integration.md) | Интеграция в текущую экосистему Warmr |
| [docs/action-plan.md](docs/action-plan.md) | План реализации по фазам |

## Статус

- [x] Ресерч и выводы записаны в docs
- [x] Стек выбран
- [x] Архитектура и план действий описаны
- [x] Контракт интеграции с экосистемой описан
- [ ] Согласование с владельцем экосистемы (лёгкость синка)
- [x] Учтены: platform_id dedupe, LLM extract, hosting Docker, sync в Warmr DB после обработки
- [ ] Старт реализации (Фаза 1 — каркас) — in progress

## Полезные ссылки

- [SearXNG GitHub](https://github.com/searxng/searxng)
- [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)
- [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview) (не foundation: closed for new / sunset 2027)
- [Playwright](https://playwright.dev)
- [Scrapy](https://scrapy.org)

## Ожидаемый результат

Поддерживаемый pipeline, который регулярно находит тысячи уникальных **релевантных и ценных** сообществ с минимальной ручной проверкой и безопасно пополняет Warmr inventory без дублей.
