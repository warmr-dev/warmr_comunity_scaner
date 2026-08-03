# Hosting & runtime

## Вопрос от команды

Куда деплоить: Railway / Render / VPS / Edge functions?  
Как часто гонять прогоны? От частоты зависит архитектура рантайма.

## Куда сохраняем

1. **Сначала** — в Postgres сканера (обработка, дедуп, classify, value).
2. **Потом** — upsert только очищенных valuable в **БД Warmr**.

Не писать сырой discovery напрямую в Warmr DB.

## Edge functions — нет

Не подходят как основной рантайм:

- длинные crawl-джобы и Scrapy
- Playwright / браузер
- Redis workers
- SearXNG рядом
- лимиты timeout/memory на edge

Edge можно максимум как тонкий trigger («запусти weekly job»), не как сам сканер.

## Рекомендация

| Режим | Когда | Где запускать |
|-------|--------|----------------|
| **Batch (MVP)** | 1–7 раз в неделю, ниши батчами | Docker-сервис на **Railway / Render**; cron/scheduler будит worker |
| **Near-24/7** | много ниш, непрерывная очередь URL | Тот же Docker worker на **Railway / Render** (always-on), + Redis/Postgres |
| **Local/dev** | отладка | `docker compose up` на машине разработчика |

**Практический выбор Warmr:** **Railway или Render** + Docker.  
VPS не нужен специально под этот микросервис (даже если DigitalOcean уже есть в инфраструктуре).

## Частота прогонов (решение по умолчанию)

Пока нет жёсткого SLA от продукта:

| Job | Частота MVP |
|-----|-------------|
| Discovery (queries/seeds) | **2–3× в неделю** или nightly по 1 нише |
| Re-fetch известных Watch/medium | **1× в неделю** |
| Sync в Warmr DB | после успешного classify, **continuous или nightly** |
| Full re-score inventory | реже (раз в 2–4 недели) |

Если позже понадобится «как только нашли — сразу в Warmr», оставляем worker 24/7 и короткий sync loop — это всё ещё Docker, не edge.

## Минимальный prod-состав

1. `worker` — pipeline
2. `scheduler` — cron внутри или платформенный cron
3. Managed **Postgres** (Railway/Render/Neon/Supabase) — можно один инстанс для scanner staging
4. Managed **Redis** (опционально на MVP; для очередей — да)
5. SearXNG — optional sidecar; Brave API не требует sidecar

## Решение (зафиксировано командой)

- Runtime: **Docker**, не Edge functions.
- Hosting target: **Railway или Render** (предпочтение команды; у Warmr это микросервис).
- VPS / DigitalOcean **не обязателен** для этого сервиса (DO есть, но для сканера не целевой).
- Данные: process in scanner DB → sync cleaned rows to Warmr DB.
- Частота: batch несколько раз в неделю на старте; always-on worker на Railway/Render возможен без смены стека.
