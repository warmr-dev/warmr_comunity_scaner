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
| `canonical_key` | text | **уникальный ключ дедупа** (см. ниже) |
| `canonical_domain` | text | host без www |
| `platform_id` | text | slug / invite code / path id на shared platforms |
| `website` | text | основной URL |
| `name` | text | название |
| `platform` | text | circle / discord / skool / slack / telegram / custom / ... |
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

Уникальность: **`canonical_key`** (unique index).

### Правило `canonical_key` (критично)

Дедуп **только по `canonical_domain` недостаточен**:

- свои сайты (`accounting-club.com`) → `canonical_key = domain`
- shared platforms (`discord.gg`, `skool.com`, `circle.so`, `t.me`, …) → много разных комьюнити на одном домене

Для platform-hosts:

```text
canonical_key = "{platform}:{platform_id}"
```

Примеры:

- `discord:AbCdEf` из `https://discord.gg/AbCdEf`
- `skool:florida-cpa` из `https://www.skool.com/florida-cpa`
- `circle:accounting-leaders` из circle community slug
- `telegram:florida_accountants` из `https://t.me/florida_accountants`
- custom site → `site:accounting-club.com`

`normalize` обязан извлекать `platform` + `platform_id` (slug/invite), иначе разные комьюнити схлопнутся в один дубль.

### `discovery_results`

Сырые URL из SearXNG до парсинга (для аудита воронки).

### `pipeline_runs`

Метрики прогона: queries, urls, fetched, accepted, rejected, new, updated, errors, duration.

## Дедуп

1. Нормализация URL → scheme/host/path cleanup.
2. Определить `platform` по host.
3. Извлечь `platform_id` (slug/invite/code) для shared platforms.
4. Построить `canonical_key` (domain **или** `platform:id`).
5. Blocklist junk hosts (google, youtube, amazon, …). LinkedIn/Facebook groups — не primary MVP source (walled garden), но домены не использовать как «одно комьюнити».
6. Перед sync в Warmr — match по `canonical_key` / domain+platform_id против существующего inventory.

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

### Extract: regex vs LLM

Regex/heuristics по сырому HTML для `price_amount` / `size_members` **часто врут** (путают цену подписки с годом основания, «$50» из другого блока и т.п.).

Пайплайн экстракции:

1. **Rules / CSS / platform parsers** — быстрый первый проход (особенно Skool/Discord/Circle шаблоны).
2. Если страница `Watch` или `value_tier=medium` / поля price|size пустые или низкая уверенность → **light LLM** (`gpt-4o-mini` или `claude-3-5-haiku`).
3. LLM возвращает строгий JSON:

```json
{
  "price": 49,
  "currency": "USD",
  "members_count": 1200,
  "is_professional": true,
  "join_type": "join|apply|unknown",
  "confidence": 0.0
}
```

LLM не гоняем на 100% URL — только на спорные/неполные, иначе дорого на масштабе.

### Walled gardens (post-MVP)

Scrapy/Playwright закрывают **публичный web**.  
Для цели ~1M хороших позже понадобятся отдельные connectors:

- Telegram API / MTProto (каналы/чаты)
- LinkedIn / Facebook groups — отдельная стратегия доступа (часто без публичного лендинга)

В MVP они **out of scope**, но в roadmap обязательны; иначе потолок inventory будет ниже цели.

## Observability

На каждый run писать:

- воронку (queries → urls → unique domains → parsed → accepted)
- error rate fetch
- playwright usage %
- new vs updated vs skipped
- sync success/fail

Без этих метрик «тысячи в неделю» нельзя отличить от «тысячи мусора».
