# warmr_comunity_scaner

Автоматический discovery + enrichment pipeline для professional communities (Warmr inventory).

Документация: [`plan.md`](plan.md) · [`docs/`](docs/)

## Быстрый старт (локально, без Docker)

Docker/Railway пока не нужны — первая версия крутится на SQLite.

```bash
cd warmr_comunity_scaner
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env

community-scanner init-db
community-scanner run --niche accounting --geo Florida --queries 3 --max-fetch 5
community-scanner list
```

Результат пишется в `data/scanner.db`. Хостинг (Railway/Render) решим позже.

## Команды

| Команда | Назначение |
|---------|------------|
| `community-scanner init-db` | Создать таблицы в Postgres |
| `community-scanner run ...` | Discovery → normalize → fetch → extract → classify → upsert |
| `community-scanner sync-dry-run` | Показать payload для Warmr DB (без записи) |

## Важные решения

- Дедуп по `canonical_key` = `site:domain` **или** `platform:platform_id` (Discord/Skool/Circle/Telegram…)
- В Warmr DB пишем **после** обработки, не сырой SERP
- LLM (`gpt-4o-mini`) — опционально для Watch/medium / слабых price&size
- Hosting: **Docker на Railway / Render** (VPS не обязателен) — см. `docs/hosting.md`

## Структура

```text
src/community_scanner/
  discovery/     # seeds, brave, searxng
  normalize.py   # platform_id + canonical_key
  extract.py     # heuristics + LLM JSON
  classify.py    # Join/Apply/Watch/Reject + value
  store.py       # Postgres upsert
  sync.py        # Warmr payload adapter
  pipeline.py    # orchestration
  cli.py
docs/
```
