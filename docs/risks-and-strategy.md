# Risks, alternatives, and revised strategy

Дата: 2026-08-03  
Вопрос: является ли путь «SearXNG → Scrapy/Playwright → Postgres → 1M» самым оптимальным?

**Короткий ответ: нет, не как единственный и сразу масштабируемый путь.**  
Это хороший **технический каркас**, но для Warmr оптимальная стратегия — **другой порядок работ** и **гибридный discovery**, иначе главные риски съедят ROI.

---

## 1. В чём ошибка «оптимальности» первого плана

Первый план оптимизировал:

- соответствие брифу (не скрейпить Google SERP),
- дешёвый self-hosted search,
- знакомый scraping-стек.

Он **недооптимизировал**:

- ценность для лидов (ground truth),
- использование уже существующих 80k,
- устойчивость discovery на объёме,
- стоимость/ops на пути к 1M,
- юридические и антибот-риски.

Для Warmr метрика успеха — не «нашли URL», а **новые комьюнити, которые дают intent-лиды вендорам**.

---

## 2. Карта рисков

### A. Продуктовые риски (самые дорогие)

| Риск | Почему больно | Митигация |
|------|----------------|-----------|
| Proxy «платный вход = ценное» ложный | Платный клуб может не генерить intent; бесплатный проф. форум может быть золотом | Учиться на ваших 20k ценных + истории лидов |
| Рост raw inventory без роста лидов | Дойдёте до «сотней тысяч», бизнес не вырастет | Синить только high/medium по value model, завязанной на лиды |
| Слишком широкий scope | Instagram/соцсети/мусорные чаты размывают фокус | Жёсткий in-scope: discoverable hubs под мониторинг |

### B. Discovery-риски

| Риск | SearXNG-only | Комментарий |
|------|--------------|-------------|
| IP ban / CAPTCHA upstream | Высокий | Google/Bing режут datacenter IP после десятков–сотен q/h |
| Тихие пустые/урезанные выдачи | Высокий | Pipeline «успешен», а кандидатов мало |
| Ops + proxies $100–300/mo | Средний/высокий | «Бесплатный search» перестаёт быть бесплатным |
| Качество выдачи нестабильно | Высокий | Зависит от набора engines и их парсеров |
| Юр./ToS серость | Средний | SearXNG часто ходит в UI search engines; бриф как раз против прямого Google scrape — дух ограничения надо уважать |

**Вывод:** SearXNG годится как **дешёвый канал / fallback**, но **опасно** делать его единственным foundation на пути к 1M.

### C. Парсинг-риски

| Риск | Уровень | Митигация |
|------|---------|-----------|
| Низкая заполняемость полей (price/size/join) | Высокий | Сначала platform-specific extractors (Circle, Skool, Discord invite pages), потом generic |
| Playwright на всё | Высокий ($$$) | Только fallback |
| Ложные Join CTA (newsletter ≠ community join) | Высокий | Правила + negative patterns |
| Ban со стороны сайтов сообществ | Средний | rate limit, robots, кэш, revisit policy |

### D. Масштаб / данные

| Риск | Уровень | Митигация |
|------|---------|-----------|
| Дубли с текущими 80k | Высокий | Обязательный match по domain до синка |
| Sheets/Airtable как SoT | Критический на 1M | Postgres only |
| Нет воронки метрик | Высокий | `pipeline_runs` + value→lead feedback loop |

### E. Интеграционные

| Риск | Уровень | Митигация |
|------|---------|-----------|
| Сканер пишет «в сторону» от Warmr schema | Высокий | sync adapter + маппинг до prod |
| Мониторинг не может взять community в работу | Высокий | обязательные поля для бота зафиксировать до синка |

---

## 3. Альтернативы discovery (сравнение)

| Канал | Качество кандидатов | Стабильность | Стоимость | Юр. риск | Роль |
|-------|---------------------|--------------|-----------|----------|------|
| **Rescore существующих 80k** | Макс. ROI сразу | Высокая | Низкая | Низкий | **Фаза 0 / must** |
| **Directory / platform seeds** (Skool, Circle directories, association lists, niche directories) | Высокий | Высокая | Низкая/средняя | Низкий/средний | **Primary supply** |
| **Brave Search API** (свой индекс) | Хороший | Высокая | ~$3–5 / 1k | Ниже, чем SERP-scrape | **Primary paid search** |
| **SerpAPI / DataForSEO** | Очень хороший (Google-like) | Высокая | Выше | Выше (SERP scrape as service) | Backup / geo-precision |
| **Self-hosted SearXNG** | Средний/плавающий | Средняя/низкая на объёме | «Free» + ops/proxies | Серый | Dev / overflow / cheap bulk |
| **Google CSE** | Хороший | — | — | Низкий | Недоступен новым; sunset 2027 |
| **Bing Web Search API** | — | — | — | — | Retired (2025) |

---

## 4. Что реально оптимально для Warmr

### Принцип

Не «найти миллион страниц».  
А **увеличивать число community, которые проходят value-фильтр и дают лиды**.

### Рекомендуемый путь (revision)

```text
Phase 0  Value model on existing 80k/20k (+ lead outcomes if available)
    ↓
Phase 1  Scanner skeleton (Postgres, dedupe, sync adapter) — без ставки на search
    ↓
Phase 2  High-signal sources: directories + platform hubs (не весь интернет)
    ↓
Phase 3  Paid search API (Brave primary) для expansion по niche×geo
    ↓
Phase 4  SearXNG as optional cheap overflow / local/dev
    ↓
Phase 5  Feedback loop: community → intents → vendor conversions → retrain value
```

### Почему так лучше

1. **80k уже есть** — самый дешёвый прирост «хороших» часто из очистки/переоценки, не из нового crawl.
2. **Directories/platforms** дают более плотных кандидатов, чем широкий web search.
3. **Brave API** ближе к брифу: официальный search API, не HTML-скрейп Google; предсказуемее SearXNG.
4. **SearXNG** оставляем, но не как single point of failure.
5. Стек Scrapy/Playwright/Postgres **остаётся верным** — меняется стратегия источников и порядок фаз.

---

## 5. Пересмотр стека (не ломаем каркас)

| Слой | Было | Стало (оптимальнее) |
|------|------|---------------------|
| Discovery primary | SearXNG | **Directories/seeds + Brave Search API** |
| Discovery secondary | — | SerpAPI/DataForSEO (по необходимости) |
| Discovery cheap/dev | — | **SearXNG** |
| Crawl | Scrapy + Playwright | без изменений |
| DB | Postgres | без изменений |
| Classify | rules | rules **обучены на ваших 20k** + lead feedback |
| Sync | adapter | без изменений; блокер до prod |

Итого: архитектура пайплайна та же, **supply strategy** умнее.

---

## 6. Когда первый план всё же ок

Оставить SearXNG-first можно, если:

- нужен дешёвый прототип за дни,
- объём queries низкий,
- команда готова чинить bans/proxies,
- цель — проверить extract/classify, а не сразу ramp to 1M.

Для заявленной цели **1M valuable** — SearXNG-first **не оптимален**.

---

## 7. Decision

**Принято как revised strategy:**

1. Не считать SearXNG-only «самым оптимальным путём».
2. Оптимальный путь = **value model → existing inventory → high-signal seeds → paid search API → SearXNG overflow**.
3. Техкаркас (Python/Scrapy/Playwright/Postgres/sync) сохраняем.
4. Перед масштабом обязателен feedback от лидов Warmr, иначе 1M будет «миллион строк», не актив.

Связанные доки: `research.md`, `stack.md`, `action-plan.md`, `integration.md`.
