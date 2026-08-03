# Architecture

## Цель системы

Еженедельно (и по запросу) находить новые **ценные professional communities**, нормализовать, классифицировать и отдавать в inventory Warmr без дублей и с минимальной ручной проверкой.

```text
┌─────────────────┐
│ Query Generator │  geo × niche × audience × type
└────────┬────────┘
         ▼
┌─────────────────┐
│ SearXNG Client  │  discovery only (JSON API)
└────────┬────────┘
         ▼
┌─────────────────┐
│ URL Normalizer  │  canonical host, drop junk hosts
│ + Deduper       │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Fetch / Parse   │  Scrapy → Playwright fallback
└────────┬────────┘
         ▼
┌─────────────────┐
│ Extractor       │  name, join, price, size, contacts...
└────────┬────────┘
         ▼
┌─────────────────┐
│ Classifier      │  Join/Apply/Watch/Reject + value_score
└────────┬────────┘
         ▼
┌─────────────────┐
│ Postgres        │  source of truth
└────────┬────────┘
         ├──────────────► Export Sheets/Airtable
         └──────────────► Warmr ecosystem sync
```

## Модули

| Модуль | Ответственность |
|--------|-----------------|
| `query_generator` | Шаблоны запросов из параметров |
| `discovery` | Клиент SearXNG, сбор SERP-подобных результатов |
| `normalize` | URL/domain canonicalization, blocklist |
| `crawler` | Scrapy spiders + Playwright fallback |
| `extract` | Поля сообщества из HTML/DOM |
| `classify` | Access status + value scoring |
| `store` | Upsert в Postgres, change detection |
| `export` | Sheets/Airtable |
| `sync` | Контракт отдачи в Warmr (API/queue/table) |
| `scheduler` | Регулярный запуск и батчинг |

## Модель данных (черновик)

### `communities`

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | uuid | PK |
| `canonical_domain` | text | ключ дедупа №1 |
| `website` | text | основной URL |
| `name` | text | название |
| `platform` | text | circle / discord / slack / custom / ... |
| `niche` | text | ниша |
| `audience` | text | аудитория (если извлекли) |
| `geo` | text | гео, если есть |
| `join_url` | text | ссылка вступления |
| `price_text` | text | сырой текст цены |
| `price_amount` | numeric | нормализованная цена (если удалось) |
| `currency` | text | |
| `size_text` | text | сырой размер |
| `size_members` | int | нормализованный размер |
| `contacts` | jsonb | email/socials |
| `access_status` | enum | join / apply / watch / reject |
| `value_score` | int | 0–100 |
| `value_tier` | enum | high / medium / low / junk |
| `relevance_score` | float | |
| `source_queries` | jsonb | какие запросы нашли |
| `raw_signals` | jsonb | признаки для отладки классификатора |
| `first_seen_at` | timestamptz | |
| `last_seen_at` | timestamptz | |
| `last_changed_at` | timestamptz | |
| `content_hash` | text | для change detection |
| `sync_status` | enum | pending / synced / error |
| `synced_at` | timestamptz | |

Уникальность: `(canonical_domain)` или `(canonical_domain, platform_id)` если известен внешний id.

### `discovery_results`

Сырые URL из SearXNG до парсинга (для аудита воронки).

### `pipeline_runs`

Метрики прогона: queries, urls, fetched, accepted, rejected, new, updated, errors, duration.

## Дедуп

1. Нормализация URL → scheme/host/path cleanup.
2. `canonical_domain` без `www.`
3. Blocklist: google/facebook/linkedin/youtube/amazon и прочие non-community хабы (расширяемый список).
4. Если один и тот же Discord/Slack invite встречается с разных лендингов — склеивать по `platform_id`, когда доступен.

## Incremental update

Считаем запись **изменённой**, если поменялись:

- `join_url`
- `price_*`
- `size_members`
- `access_status`
- `value_tier`
- `name` (существенно)

В экосистему уходят:

- новые `value_tier in (high, medium)` и `access_status != reject`
- изменённые по полям выше

Reject и junk можно хранить локально (чтобы не находить повторно), но не синкать как «хорошие».

## Классификатор (логика MVP)

### Access status

- Есть CTA `join` / `sign up` / `become a member` без application → **Join**
- Есть `apply` / `request to join` / `waitlist` → **Apply**
- Страница похожа на community, но CTA/данных мало → **Watch**
- Не community / directory spam / irrelevant → **Reject**

### Value score (эвристики)

Плюсы:

- paid membership
- members >= порога
- niche keywords match
- geo match (если запрос гео-sensitive)
- professional language / association markers

Минусы:

- очень мало members
- no niche
- thin page / parked domain
- known low-quality patterns

LLM — опциональный второй проход для Watch и спорных medium.

## Observability

На каждый run писать:

- воронку (queries → urls → unique domains → parsed → accepted)
- error rate fetch
- playwright usage %
- new vs updated vs skipped
- sync success/fail

Без этих метрик «тысячи в неделю» нельзя отличить от «тысячи мусора».
