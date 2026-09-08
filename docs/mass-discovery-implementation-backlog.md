# Mass discovery — implementation backlog

Основано на [`docs/mass-discovery-research.md`](mass-discovery-research.md).  
Скоуп: без Discord/Telegram primary; цель — сырой объём кандидатов.

Не реализовывать всё сразу. Порядок = выбранные каналы A → structured seeds → schema.

---

## P0 — Schema: raw candidates vs communities

### Новая таблица `raw_candidates`

| Поле | Тип | Зачем |
|------|-----|--------|
| `id` | uuid | PK |
| `url` | text | исходный URL |
| `canonical_key` | text | nullable до normalize |
| `platform` | text | nullable |
| `platform_id` | text | nullable |
| `source_provider` | text | `commoncrawl`, `dataforseo`, `brave`, `hive`, … |
| `source_record_id` | text | CDX urlkey / SERP hash / hive slug |
| `title` | text | optional |
| `snippet` | text | optional |
| `raw_payload_hash` | text | dedupe payload |
| `community_likelihood` | float | 0–1 cheap score |
| `status` | enum | `new` / `normalized` / `rejected` / `promoted` |
| `discovered_at` | timestamptz | |
| `processed_at` | timestamptz | |

Unique: `(source_provider, source_record_id)` или `raw_payload_hash`.

`discovery_results` можно оставить для SERP audit; `raw_candidates` — единый вход для всех bulk providers.

### Метрики `pipeline_runs.metrics` (добавить)

```json
{
  "provider": "commoncrawl",
  "raw_urls": 0,
  "unique_keys": 0,
  "new_vs_inventory": 0,
  "dup_ratio": 0.0,
  "likelihood_pass": 0,
  "promoted": 0,
  "blocked": 0,
  "cost_usd_est": 0.0,
  "duration_ms": 0
}
```

---

## P0 — Provider: Common Crawl CDX

**Файл:** `src/community_scanner/discovery/commoncrawl.py`  
**Интерфейс:** `DiscoveryProvider` (+ опционально `crawl_patterns(patterns, limit)`).

### Поведение

1. Читать `collinfo.json` → latest `cdx-api` (smoke: `CC-MAIN-2026-34`).
2. Паттерны без Discord/Telegram primary:

```text
*.skool.com/*
*.circle.so/*
join.slack.com/t/*
chat.whatsapp.com/*
*.mightynetworks.com/*
www.facebook.com/groups/*
www.linkedin.com/groups/*
old.reddit.com/r/*
*/categories.json
```

3. Пагинация CDX (`page` / resume urlkey) с retry на 503.
4. Normalize → extract platform_id → write `raw_candidates`.
5. Cheap likelihood:
   - Skool slug page /about → high
   - Slack `join.slack.com/t/{workspace}/shared_invite/...` → high
   - Facebook/LinkedIn group id → medium
   - marketing homepage noise (`circle.so/blog`) → low/reject

### CLI

```bash
community-scanner discover --providers commoncrawl --max-raw 50000
```

### Env

```text
COMMONCRAWL_INDEX=CC-MAIN-2026-34   # or "latest"
COMMONCRAWL_CDX_DELAY_MS=800
COMMONCRAWL_MAX_PAGES_PER_PATTERN=0  # 0 = until empty / budget
```

### Later (million-scale)

Отдельный job: Athena SQL по `s3://commoncrawl/cc-index/table/...` с теми же URL filters; экспорт parquet → import в `raw_candidates`.

---

## P0 — Provider: DataForSEO SERP

**Файл:** `src/community_scanner/discovery/dataforseo.py`

### Поведение

1. Task POST standard queue (cheapest).
2. Queries из расширенного `generate_queries` + platform operators:

```text
site:skool.com "{niche}"
site:circle.so "{niche}"
inurl:join.slack.com "{niche}"
site:facebook.com/groups "{niche}"
site:linkedin.com/groups "{niche}"
"{niche}" "{geo}" community OR forum OR membership
"powered by Discourse" "{niche}"
```

3. Parse organic URLs → `raw_candidates` with `source_provider=dataforseo`.

### Env

```text
DATAFORSEO_LOGIN=
DATAFORSEO_PASSWORD=
DATAFORSEO_MODE=standard   # standard|priority|live
```

### Почему не Brave first

Brave уже есть, но **~$5/1k** vs DataForSEO **~$0.60/1k** standard. Brave = secondary / diversity.

Wire: добавить `dataforseo` в `build_providers()` рядом с `brave`.

---

## P0 — Structured: Hive Index full harvest

Уже есть `scripts/import_from_hive_index.py`.

### Доделать

1. Обойти **все** platform + topic pages (не только hardcoded 10 topics).
2. Писать сначала в `raw_candidates`, потом promote.
3. Исключить Telegram listings если `EXCLUDE_TELEGRAM=true` / platform allowlist.
4. Метрика: community pages crawled, invites extracted, new keys.

Ожидание: тысячи high-signal records, не миллион — но лучший precision bootstrap.

---

## P1 — Skool from Common Crawl (not discovery UI)

UI `/discovery` вернул **HTTP 202** challenge — не использовать как prod source.

### Flow

1. CC pattern `*.skool.com/*` → unique slugs.
2. Reuse `scripts/import_real_skool_discovery.py` / `import_free_skool.py` logic as provider `skool_cc`.
3. Fetch `/about` only for new slugs; skip enrich in harvest mode.

---

## P1 — Circle structured

1. CC `*.circle.so/*` → candidate hosts/slugs.
2. Reverse-engineer current discover.circle.so XHR (home SPA loads; old `public_api/spaces` 404).
3. Provider `circle_directory` when endpoint stable.
4. Temporary: Apify actor only for benchmark, not core.

---

## P1 — Discourse host discovery + JSON connector

1. Hosts from: SERP (`"powered by Discourse"`), CC (`*/categories.json` with better prefixes), seed list in `data/discourse_hosts.txt`.
2. Provider `discourse`: for each host GET `/categories.json` → one community record per forum (or per category if product wants finer grain).
3. Smoke already OK: meta.discourse.org, community.openai.com, discuss.huggingface.co.

---

## P1 — Reddit OAuth provider

Unauthenticated `/subreddits/search.json` → 403.

1. Register app; env `REDDIT_CLIENT_ID/SECRET/USER_AGENT`.
2. Provider uses `GET /subreddits/search` with OAuth; respect 100 QPM.
3. Store `reddit:{subreddit}`.

---

## P1 — Query compiler upgrade

Расширить `generate_queries` / templates:

- niche × geo × audience × platform operator
- negative terms (jobs, careers, wikipedia, amazon)
- persist per-query yield in DB; retire noisy templates weekly

---

## P2 — Observability dashboard

API `/api/stats` расширить:

- raw_candidates count by provider/status
- promotion rate
- cost estimate
- top templates by new keys

---

## P2 — Deprioritize Discord/Telegram directory in this mode

Когда `MASS_DISCOVERY_MODE=true` / `DISCOVERY_PROVIDERS` без `directory`:

- не запускать tgstat/disboard/discordservers
- templates без telegram (уже можно вырезать флагами)
- оставить telegram только если явно в allowlist

---

## Suggested 2-week build order

| Day | Work |
|-----|------|
| 1–2 | `raw_candidates` table + migrate + store helpers |
| 3–4 | `CommonCrawlProvider` + CLI smoke 50k rows |
| 5 | Likelihood filter + promote → `community_scanner` |
| 6–7 | `DataForSEOProvider` + 1k niche×geo queries budget test |
| 8 | Hive full crawl into raw_candidates |
| 9 | Skool slug pipeline from CC |
| 10 | Metrics comparison report vs baseline 12k |
| 11–14 | Discourse hosts + Reddit OAuth + Circle reverse API |

### Success criteria (first wave)

1. `raw_candidates` ≥ **100k** unique keys from CC+Hive+SERP in one week of runs.  
2. After dedupe vs existing ~12k: ≥ **50k new**.  
3. Cost for SERP portion tracked; CC cost ≈ storage/compute only.  
4. Provider-level metrics in `pipeline_runs`.  
5. No dependency on Discord/Telegram directories for the wave.

---

## File touch list (concrete)

- `src/community_scanner/discovery/commoncrawl.py` (new)
- `src/community_scanner/discovery/dataforseo.py` (new)
- `src/community_scanner/discovery/__init__.py` — register providers
- `src/community_scanner/config.py` — env settings
- `src/community_scanner/models/db.py` — `RawCandidate` model
- `src/community_scanner/store.py` — upsert raw / promote
- `src/community_scanner/cli.py` — flags `--providers`, `--max-raw`
- `supabase/community_scanner.sql` or alembic migration
- `scripts/import_from_hive_index.py` — align to raw_candidates
- `.env.example` — new keys
- `tests/test_commoncrawl_normalize.py`, `tests/test_raw_candidates.py`
