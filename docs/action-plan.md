# Action Plan

## Статус

Документация и решения по стеку/архитектуре — готовы.  
Дальше — реализация в этом репозитории.

## Фаза 0 — Документация + стратегия (done)

- [x] Зафиксировать продуктовый контекст Warmr
- [x] Выбрать стек
- [x] Описать архитектуру и модель данных
- [x] Описать интеграцию с экосистемой
- [x] Составить план работ
- [x] Разобрать риски и revised strategy (`risks-and-strategy.md`)

## Фаза 0.5 — Value model на существующих данных (до масштаба search)

- [ ] Выгрузить sample из текущих ~80k / ~20k ценных
- [ ] Зафиксировать признаки «ценного» на реальных примерах (+ лиды, если доступны)
- [ ] Черновик scorer; прогнать на sample; замерить precision/recall грубо
- [ ] Правило: что синкать в экосистему

**Результат:** value_tier опирается на Warmr-реальность, не на догадку «paid = good».

## Фаза 1 — Каркас репо (1–2 дня)

- [ ] Структура проекта Python (`src/community_scanner/...`)
- [ ] `pyproject.toml` / dependencies
- [ ] Docker Compose: Postgres + Redis (+ optional SearXNG)
- [ ] Settings через `.env.example` (в т.ч. Brave API key)
- [ ] Alembic + таблица `communities` / `pipeline_runs`
- [ ] README с запуском local

**Результат:** `docker compose up` поднимает инфраструктуру, приложение коннектится к БД.

## Фаза 2 — Discovery MVP (2–4 дня)

- [ ] Seed/directory connectors (high-signal источники) — primary
- [ ] Brave Search API client — primary paid search
- [ ] Query generator (шаблоны: niche/geo/audience/type)
- [ ] SearXNG client — optional overflow/dev
- [ ] Provider abstraction: `DiscoveryProvider` (brave | seeds | searxng | serp_backup)
- [ ] URL normalize + domain dedupe + blocklist + match against existing inventory
- [ ] Smoke: seeds + 20–50 search queries → уникальные домены

**Результат:** кандидаты из плотных источников + search, без ставки только на SearXNG.

## Фаза 3 — Parse + Extract (3–5 дней)

- [ ] Scrapy spider по кандидатам
- [ ] Extrators: title/name, join links, price hints, size hints, contacts
- [ ] Playwright fallback для пустых/JS страниц
- [ ] Respectful rate limits / retries
- [ ] Upsert в `communities`

**Результат:** из кандидатов получаем структурированные записи.

## Фаза 4 — Classify + Value (2–3 дня)

- [ ] Rules для Join / Apply / Watch / Reject
- [ ] Heuristics `value_score` / `value_tier`
- [ ] Опционально LLM-pass для Watch
- [ ] Метрики воронки в `pipeline_runs`

**Результат:** фильтр «ценных» работает без ручного разбора каждой строки.

## Фаза 5 — Export + Sync adapter (2–3 дня)

- [ ] Export в Google Sheets и/или Airtable
- [ ] Adapter `sync` (JSON upsert contract)
- [ ] Флаги: sync only high/medium, new/changed only
- [ ] Сверить формат с владельцем Warmr inventory

**Результат:** понятная точка интеграции в текущую экосистему.

## Фаза 6 — Hardening (ongoing)

- [ ] Scheduler (weekly / daily niche batches)
- [ ] Observability / алерты error rate
- [ ] Расширение query templates под US niches (accounting и др.)
- [ ] Улучшение value model на реальной разметке
- [ ] Масштабирование workers

## Порядок запуска прямо сейчас

1. Согласовать этот план с владельцем репо / экосистемы (коротко).
2. Начать **Фазу 1** в этом репозитории.
3. Не ждать идеального ответа по интеграции: sync — отдельный адаптер.
4. Первый вертикальный срез: 1 ниша + 1 гео (например accounting + Florida) end-to-end.

## MVP success criteria

Pipeline считается успешным MVP, если:

1. За один прогон на ограниченном наборе параметров находит **новые** комьюнити, которых нет в локальной БД сканера.
2. Доля `reject/junk` объяснима и не заливает export.
3. Есть стабильные поля: name, website, access_status, value_tier.
4. Повторный прогон не плодит дубли.
5. Есть понятный путь синка в Warmr (даже если сначала Sheets/Airtable).

## Не делаем в MVP

- Мониторинг лент / intent detection
- Матчинг vendor ↔ lead
- Массовый скрейпинг Google SERP HTML
- Instagram-first discovery
- Попытка сразу закрыть цель 1M без рабочей воронки и метрик
