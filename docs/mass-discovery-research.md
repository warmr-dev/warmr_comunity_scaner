# Mass discovery research

Дата: 2026-09-08  
Скоуп: максимизировать **сырой объём** community-кандидатов; **без Discord/Telegram как primary**.  
Текущий inventory (заявка): ~12 000.

Сырые артефакты прогонов:

- [`docs/mass-discovery-smoke.json`](mass-discovery-smoke.json)
- [`docs/mass-discovery-smoke-extra.json`](mass-discovery-smoke-extra.json)
- [`docs/mass-discovery-cc-volume.json`](mass-discovery-cc-volume.json)
- скрипты: `scripts/research_mass_discovery_smoke.py`, `*_extra.py`, `*_cc_volume.py`

---

## 1. Baseline текущего pipeline

### Что есть сейчас

| Слой | Состояние |
|------|-----------|
| Providers | `seeds`, `brave`, `ddg`, `bing`, `directory`, `searxng` (`build_providers` в `src/community_scanner/discovery/__init__.py`) |
| Default prod | `directory,searxng` — directory сейчас тянет **tgstat / disboard / discordservers** (не наш целевой скоуп) |
| Query gen | Harvest templates: Slack, Skool, Circle, FB, LI, Hive, WA, Telegram (`discovery/base.py`) |
| Dedupe | `canonical_key = platform:id` или `site:domain` (`normalize.py`) |
| Upsert filter | `ACTIVE_HARVEST_PLATFORMS` **включает** telegram/reddit/…, **не включает** discord (`invites.py`) |
| Store | `community_scanner` + `discovery_results` + `pipeline_runs` |
| Готовые скрипты | Hive import, Skool import, public social (Reddit/GitHub/SE/Matrix/Zulip/Discourse), bulk_fill |

### Почему объём ~12k — узкое горлышко

1. Discovery идёт через **SERP HTML / SearXNG** (мало результатов на query, баны, нестабильность).
2. Prod directory provider заточен под **Telegram/Discord catalogs**, а не под bulk web/platform dumps.
3. Нет отдельного **raw_candidates** слоя: всё пытается сразу стать community row.
4. Skool/Circle discovery UI **бот-защищены**; без platform/bulk index они почти не масштабируются.
5. Reddit без OAuth → 403.
6. Нет массового offline index (Common Crawl / Athena).

### Baseline metrics (как измерять дальше)

На каждый provider/run фиксировать:

`queries → raw_urls → unique_canonical_keys → new_vs_existing_12k → community_likelihood → fetch_ok → cost`

---

## 2. Smoke-результаты по источникам

| Источник | Smoke | Сигнал объёма | Качество структуры | Блокировки | Вывод |
|----------|-------|---------------|--------------------|------------|--------|
| **Common Crawl CDX** (`CC-MAIN-2026-34`) | OK через `collinfo` | Skool/Slack/Circle/Mighty: **hit limit 200** на выборке → индекс глубже sample; Slack: **183 unique keys / 200 rows** | URL-only; нужен normalize | CDX иногда 503/502 при параллели | **#1 bulk** |
| **Hive Index** | OK | 5 platform pages → **1141 unique `/communities/`**; detail отдаёт join URL (Skool sample) | Высокое | Нет | **#1 structured seed**, не million-source (~5.6k claimed) |
| **Circle discover** | Home 200, guessed `public_api` 404 | SPA /goals; 91 href | Нужен reverse API или CC | HTML API paths устарели | Structured через CC + reverse API |
| **Skool discovery UI** | **202** challenge page | UI почти бесполезен без browser/login | — | Anti-bot | Брать через **CC + existing scripts** |
| **Reddit JSON** | 403 / HTML welcome | — | Хороший при OAuth | Без OAuth блок | Нужен **OAuth** или third-party |
| **Discourse `/categories.json`** | OK на 3 hosts | ~5k+ forums в экосистеме, но hosts надо найти | Отличный JSON | Низкий на known hosts | Structured connector после host discovery |
| **Forum Finder** | OK UI | Не bulk API | Search-only | — | Не foundation |
| **DataForSEO SERP** | Не live (нет ключа) | Pay-as-you-go **~$0.60 / 1k SERP** (10 results) | SERP URLs | Официальный API | **#1 fresh/cost** |
| **Brave Search API** | Клиент уже в коде; ключ пустой | **~$5 / 1k** | SERP URLs | Официальный API | Fresh backup / уже wired |
| **DDG/Bing HTML / SearXNG** | Уже в prod | Низкий throughput | Шумный | CAPTCHA/ban | Overflow only |

### Common Crawl — практический сигнал

Успешный probe:

```text
https://index.commoncrawl.org/CC-MAIN-2026-34-index?url=*.skool.com/*&output=json&limit=10
→ реальные skool.com/{slug}/about URL
```

`join.slack.com/t/*` в sample 200 строк → **183 уникальных slack workspaces**.  
Это доказывает: **pattern crawl CDX даёт плотные platform IDs без SERP**.

Facebook/LinkedIn/Reddit CDX patterns с этой машины дали 404/502 — нужны другие URL prefixes (`www.facebook.com/groups/*`, `old.reddit.com/r/*`) и/или Athena bulk query, не отказ от канала.

---

## 3. Сравнение (одинаковые критерии)

Оценки для цели **raw volume**, без Discord/Telegram primary.

| Provider | Raw/hour potential | New after 12k dedupe | Dup risk | Community-likelihood | Cost / 1k new | Legal/ops | Score |
|----------|--------------------|----------------------|----------|----------------------|---------------|-----------|-------|
| Common Crawl CDX/Athena | Очень высокий | Высокий | Средний (нужен strong normalize) | Средний (URL heuristics) | ≈ compute only | Open data; rate-limit CDX | **A** |
| DataForSEO | Высокий (управляемый) | Высокий на gaps | Низкий–средний | Средний–высокий (query design) | ~$0.06–$0.60+ depending depth | Official API | **A** |
| Brave (existing) | Средний–высокий | Средний | Низкий–средний | Средний–высокий | ~$5 / 1k queries | Official; already coded | **B+** |
| Hive Index crawl | Низкий–средний ceiling (~5–10k) | Средний сейчас | Низкий | **Высокий** | Низкая | Public HTML; polite crawl | **A for quality seeds** |
| Skool via CC + scripts | Средний–высокий | Высокий | Средний | Высокий на slug pages | Низкая | Public pages; UI anti-bot | **A** |
| Circle via CC + API reverse | Средний | Средний | Средний | Высокий | Низкая–средняя | Public discover | **B+** |
| Reddit OAuth search | Средний (100 QPM) | Средний | Низкий | Высокий | Free tier limits | Official OAuth required | **B** |
| Discourse host list + JSON | Средний | Средний | Низкий | Высокий | Низкая | Public JSON | **B+** |
| SearXNG/DDG/Bing HTML | Низкий | Низкий | Высокий noise | Низкий–средний | Ops/proxy | Unstable | **C** |
| Apify actors | Средний quick win | Средний | Vendor lock | Высокий на niche scrapers | $/result | ToS/vendor | **B experiment only** |

---

## 4. Выбор архитектуры (3 слоя)

```text
Bulk index (Common Crawl)
        \                    → raw_candidates
Fresh SERP (DataForSEO primary, Brave secondary)
        /                         ↓
Structured (Hive, Skool/CC, Circle, Discourse hosts, Reddit OAuth)
                                  ↓
                     normalize + dedupe (canonical_key)
                                  ↓
                     cheap community-likelihood filter
                                  ↓
                     communities inventory (Postgres)
```

### Выбранные 2–3 лучших канала для внедрения первыми

1. **Common Crawl provider** — главный рывок raw volume (Skool/Slack/Circle/Mighty/WA patterns).  
2. **DataForSEO SERP provider** — дешёвый targeted expansion niche×geo×platform (дешевле Brave ~8×).  
3. **Structured pack:** Hive Index full crawl + Skool from CC + Discourse host discovery + Reddit OAuth later.

Brave оставить как уже реализованный paid backup.  
SearXNG/DDG — overflow.  
Directory tgstat/disboard — **не primary** в этом скоупе.

---

## 5. Риски

- CDX public API нестабилен (503) → для million-scale нужен **Athena/Spark по columnar index**, CDX — для smoke/incremental patterns.
- Raw volume ≠ useful communities: без likelihood filter зальём junk.
- Facebook/LinkedIn groups — walled garden; CC URL list ≠ joinable inventory.
- Skool UI anti-bot; не строить prod на `/discovery` HTML.
- Reddit без OAuth не работает.
- Apify — ок для эксперимента, не core dependency.

---

## 6. Следующий шаг

См. [`docs/mass-discovery-implementation-backlog.md`](mass-discovery-implementation-backlog.md).
