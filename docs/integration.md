# Integration with Warmr ecosystem

## Зачем этот документ

Коллега отдельно попросил: перед активной разработкой зафиксировать, что тул **легко интегрируется** в текущую экосистему.

Этот сканер **не заменяет**:

- ботов мониторинга лент
- матчинг intent → vendor
- биллинг вендоров

Он только **расширяет inventory комьюнити**, из которого мониторинг уже берёт источники.

## Текущий контекст экосистемы

Из продуктового объяснения:

- есть vendors (плательщики за лиды)
- есть communities (источники intent)
- в БД уже ~80k грязных / ~20k ценных
- цель — расти к ~1M хороших

Значит интеграция = аккуратно **добавлять/обновлять** записи в существующий inventory, а не плодить параллельную «истину».

## Принцип интеграции

```text
warmr_comunity_scaner (Postgres / export)
        │
        │  только new + changed, valuable
        ▼
Warmr Communities Inventory  ──► monitoring bots ──► intent leads ──► vendors
```

Сканер = upstream supply.  
Мониторинг/лиды = downstream consumption.

## Рекомендуемый контракт синка (v1)

Минимальный payload одной community:

```json
{
  "external_id": "uuid-from-scanner",
  "canonical_domain": "example.com",
  "website": "https://example.com",
  "name": "Florida Accountants Network",
  "platform": "circle",
  "niche": "accounting",
  "audience": "CPAs and bookkeepers",
  "geo": "Florida, US",
  "join_url": "https://example.com/join",
  "price_amount": 49,
  "currency": "USD",
  "size_members": 1200,
  "contacts": {"email": "hello@example.com"},
  "access_status": "join",
  "value_score": 78,
  "value_tier": "high",
  "source": "community_scanner",
  "content_hash": "sha256:...",
  "discovered_at": "2026-08-03T12:00:00Z",
  "changed_at": "2026-08-03T12:00:00Z"
}
```

### Транспорт (выбрать один при стыковке с экосистемой)

В порядке предпочтения для лёгкой интеграции:

1. **Таблица/очередь в уже существующей Warmr DB** (`communities_inbound`) — самый простой ops-путь, если есть общий Postgres.
2. **HTTP webhook / internal API** `POST /internal/communities/upsert` — если сервисы разделены.
3. **Очередь** (Redis/SQS/Rabbit) с тем же JSON — если уже event-driven.
4. **Airtable/Sheets** — только временный human-facing bridge, не идеальный prod-sync на миллион.

## Идемпотентность

Чтобы не засорять базу:

- upsert по `canonical_domain` (или по Warmr community id, если уже смапили)
- не создавать дубль, если домен уже есть в 80k
- scanner хранит `sync_status` / `synced_at`
- повторный weekly run безопасен

## Фильтр «что вообще синкать»

В экосистему по умолчанию:

- `access_status in (join, apply, watch)` — Watch можно отдельным флагом
- `value_tier in (high, medium)`
- не синкать `reject` / `junk` как «хорошие»

Так мы увеличиваем именно **ценный** inventory, а не сырой счётчик.

## Что нужно уточнить у владельцев экосистемы (1 раз перед prod-sync)

Не блокирует старт сканера, но нужно до первого боевого синка:

1. Где сейчас живут 80k/20k — какая схема таблицы communities?
2. Есть ли уже unique key по domain/url?
3. Какие поля обязательны, чтобы мониторинг-бот мог взять community в работу?
4. Предпочтительный транспорт: DB table / API / queue?
5. Нужен ли human approval на `watch` перед попаданием в мониторинг?

Пока этих ответов нет, реализуем сканер end-to-end с Postgres + export, а `sync` делаем адаптером под их контракт.

## Почему интеграция будет лёгкой

| Решение сканера | Польза для экосистемы |
|-----------------|------------------------|
| Postgres + стабильная схема | Легко маппить в текущую БД |
| Dedup по domain | Не раздуваем 80k дублями |
| Incremental new/changed | Неполный reimport каждую неделю |
| value_tier отдельно от Join/Apply | Можно кормить мониторинг только high/medium |
| sync adapter слой | Не привязаны к Sheets навсегда |
| pipeline_runs метрики | Видно, растём ли к 1M качественно |

## Definition of Done для интеграции

- [ ] Описан маппинг полей scanner → Warmr communities
- [ ] Выбран транспорт синка
- [ ] Upsert идемпотентен на тестовом батче
- [ ] В мониторинг не утекает reject/junk
- [ ] Есть счётчик `new valuable synced / week`
