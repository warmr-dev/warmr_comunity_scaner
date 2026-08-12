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

## Частота прогонов (целевой режим)

| Job | Частота |
|-----|---------|
| Discovery (Brave Search) | **2× в день** (cron) |
| Fetch worker (Redis queue) | в том же cron (`SCANNER_MODE=full`) или отдельный always-on worker |
| Re-fetch Watch/medium | 1× в неделю (отдельный cron с `SCANNER_MODE=worker`) |
| Sync в Warmr DB | после успешного classify |

Тайминги и env: [`supabase-brave-setup.md`](supabase-brave-setup.md).

## Минимальный prod-состав

1. `scanner` — discovery + fetch (`SCANNER_MODE=run` или `full`)
2. **Cron** — Railway scheduler 2×/день
3. **Supabase Postgres** — `community_scanner`
4. **Brave Search API key** — `BRAVE_SEARCH_API_KEY`

## Решение (зафиксировано командой)

- Runtime: **Docker**, не Edge functions.
- Hosting target: **Railway или Render** (предпочтение команды; у Warmr это микросервис).
- VPS / DigitalOcean **не обязателен** для этого сервиса (DO есть, но для сканера не целевой).
- Данные: process in scanner DB → sync cleaned rows to Warmr DB.
- Частота: batch несколько раз в неделю на старте; always-on worker на Railway/Render возможен без смены стека.
