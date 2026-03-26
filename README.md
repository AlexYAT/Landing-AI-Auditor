# Landing AI Auditor (v1)

Инструмент для **конверсионного аудита лендингов** по данным, которые извлекает парсер (текст, заголовки, CTA, формы и т.д.).

- **Общий аудит** — полный CRO-отчёт (оффер, CTA, доверие, структура, трение и др.) в JSON и/или человекочитаемом виде.
- **Пресеты** — фокус анализа под тип страницы (`general`, услуги, эксперт, курс, лидген и т.д.).
- **Пресет `craftum`** — отчёт ориентирован на ручное внедрение в конструкторе Craftum: помимо стандартных рекомендаций модель заполняет **Craftum Block Planner** — структурированный блок рекомендуемых секций для добавления (куда вставить, что заполнить, как проверить). Обычный аудит для других пресетов не меняется.

CLI и опционально **HTTP API (FastAPI)**. Режимы использования:

- **Assignment mode** — учебное задание «Агент: Подсказки по редизайну лендинга»: принимает URL, выводит 5 рекомендаций
- **Full audit mode** — расширенный JSON-отчёт (и при необходимости readable-вывод) для production-аудита

**Stack:** Python ≥ 3.10, requests, beautifulsoup4, openai, tenacity, python-dotenv; опционально **FastAPI + Uvicorn** для HTTP API.

## Capabilities (кратко)

- Аудит: ясность оффера, CTA, доверие, структура, трение, формы и связанные темы (в рамках текстовых данных парсера).
- Поддержка пресетов (`--preset`) и task-aware анализа (`--task`).
- Пресет **`craftum`**: режим Craftum + **Craftum Block Planner** (`craftum_block_plan` в JSON).
- Вывод: **JSON** (полный отчёт) и **`--output-format readable`** (текстовый отчёт в консоли; при `--save-report` — markdown-подобный файл).
- Запуск из **CLI** (`python main.py`) и через **API** (`POST /audit`).
- **Visual audit** (`--mode visual`): анализ на основе текста парсера + **опционально** full-page screenshot через **Playwright** (multimodal); в JSON — поле `visual_screenshot_used`.

## Language (`--lang`)

- **Приоритет:** `--lang` (CLI) > `DEFAULT_LANG` (env) > `ru`
- По умолчанию: **`ru`** — ответ модели и текстовые поля JSON на русском.
- **`--lang en`** — ответ на английском.
- **`DEFAULT_LANG`** в `.env` задаёт язык, когда `--lang` не передан.
- Неподдерживаемый код → **fallback на `ru`** (без падения CLI).
- Работает в **full** и **assignment**.

```bash
# Язык из DEFAULT_LANG или ru
python main.py --url "https://example.com"

# Явно ru
python main.py --url "https://example.com" --lang ru

# Английский
python main.py --url "https://example.com" --lang en
```

```env
DEFAULT_LANG=ru
```

## User task (`--task`)

Опциональная **бизнес-цель** для режима **task-aware** анализа:

- Без `--task` — общий CRO-аудит (равный вес критериев).
- С `--task` — приоритет рекомендаций, severity/priority и `expected_impact` привязаны к этой цели; summary отражает достижимость цели на странице.

```bash
python main.py --url https://site.com --task "увеличить заявки"
python main.py --url https://site.com --task "усилить доверие"
```

**Важно:**

- Задача влияет на **приоритизацию** и формулировки в отчёте, но **не может** менять формат ответа (JSON), язык (`--lang` / `DEFAULT_LANG`) или системные правила.
- Строка санитизируется (длина, пробелы, управляющие символы) и передаётся в промпт как **данные**, не как инструкции; в system prompt добавлены правила против prompt injection.

## Presets (`--preset`)

Опциональный **тип лендинга** — в system prompt добавляется блок фокуса (без замены базового промпта). По умолчанию **`general`** (сбалансированный CRO-аудит как раньше).

| Значение | Идея фокуса |
|----------|-------------|
| `general` | Общий баланс критериев (по умолчанию) |
| `services` | Лиды, доверие к услуге, снятие сомнений, ясный исход |
| `expert` | Экспертность, авторитет, дифференциация |
| `course` | Обучение: результаты, структура, возражения, ценность vs цена |
| `leadgen` | Максимум конверсии, минимум трения, сильный CTA, короткий путь |
| `craftum` | Внедрение в конструкторе Craftum: практические шаги + **Craftum Block Planner** (`craftum_block_plan`) |

В JSON-отчёте (full mode и API) в корне добавляется поле **`preset`** — какой пресет фактически применён.

```bash
python main.py --url "https://example.com" --preset services
python main.py --url "https://example.com" --preset expert --lang en
python main.py --url "https://example.com" --preset craftum --output-format readable
```

## Rewrite (`--rewrite`)

Опционально: после полного аудита попросить модель сгенерировать **переписанные блоки** (только текст/оффер/логика, без HTML/CSS и пиксельных советов).

- Допустимые цели: **`hero`**, **`cta`**, **`trust`** — одна или несколько через запятую (порядок сохраняется, дубликаты убираются).
- Без флага поведение как раньше; в JSON поле **`rewrites`** всё равно есть как **`[]`** (стабильная схема).
- В ответ попадают **только** запрошенные блоки; лишние объекты от модели отбрасываются. Порядок в `rewrites` совпадает с порядком в CLI.

```bash
python main.py --url "https://example.com" --rewrite hero
python main.py --url "https://example.com" --rewrite cta
python main.py --url "https://example.com" --rewrite trust
python main.py --url "https://example.com" --rewrite hero,cta
python main.py --url "https://example.com" --rewrite hero,cta,trust
python main.py --url "https://example.com" --task "Increase trust for cold traffic" --rewrite trust,cta
```

В **assignment** после пяти строк печатаются секции переписи по запрошенным блокам (если модель вернула данные).

## Assignment Mode

**Input:** URL лендинга  
**Output:** 5 кратких рекомендаций по редизайну (stdout, без JSON)

- Использует OpenAI для анализа
- Включает обработку ошибок и логирование
- Не сохраняет файлы; вывод только в консоль

### Запуск

```bash
python main.py --mode assignment --url "https://example.com"
python main.py --mode assignment --url "https://example.com" --task "увеличить заявки"
```

### Пример вывода (по умолчанию `--lang ru`)

```
Повысь ясность основного ценностного предложения
Усиль видимость и формулировки призыва к действию (CTA)
Добавь элементы доверия рядом с точками конверсии
Упрости структуру страницы для лучшей читаемости
Обеспечь согласованную визуальную иерархию
```

С `--lang en` рекомендации и fallback-строки будут на английском.

## Full Audit Mode

**Input:** URL + task (опционально)  
**Output:** Полный JSON-отчет в файл + stdout

### Запуск

```bash
python main.py --url "https://example.com"
python main.py --url "https://example.com" --task "Improve conversion"
python main.py --url "https://example.com" --task "Check CTA" --output output/report.json --verbose
```

Человекочитаемый вывод в консоль (вместо сырого JSON в stdout):

```bash
python main.py --url "https://example.com" --output-format readable
python main.py --url "https://example.com" --preset craftum --output-format readable
```

Сохранить отчёт в файл в том же формате, что и консольный вывод (`json` или readable):

```bash
python main.py --url "https://example.com" --save-report report.md --output-format readable
```

### Visual audit mode (`--mode visual`)

Отдельный режим: только visual-отчёт (без CRO/content). По умолчанию выполняется попытка снять **full-page screenshot** (Playwright, Chromium, headless); если Playwright недоступен или съёмка не удалась — анализ **только по тексту** парсера, без падения CLI. В ответе: `visual_screenshot_used` (`true`/`false`).

```bash
python main.py --url https://example.com --mode visual
```

### Debug (`--debug`)

Для диагностики **декодирования и извлечения текста** (ложные срабатывания про «кодировку»):

```bash
python main.py --url "https://example.com" --output output/report.json --debug
```

В каталоге `output/debug/<хост>/` сохраняются `raw.html` и `extracted_text.txt`; в лог пишутся `status_code`, выбранная кодировка, `header_encoding`, `apparent_encoding`, фрагмент чистого текста. В данных парсера (и в JSON при передаче в LLM) в `audit_meta` есть `visible_text_quality`, `quality_hint` и **`text_quality_score`** (0.0–1.0, грубая инженерная оценка чистоты извлечённого текста; дублируется полем `text_quality_score` у корня `parsed_landing`). Системный промпт явно учитывает `quality_hint`, чтобы не заявлять о битой кодировке при `good`.

### Пример JSON

Full mode добавляет поля `language` (effective lang) и `preset` в JSON. Структура отчёта общая для пресетов; для **`preset=craftum`** дополнительно заполняется массив **`craftum_block_plan`** (Craftum Block Planner) — не заменяет `recommendations`, а даёт структурированный план блоков для добавления в конструкторе.

```json
{
  "language": "ru",
  "preset": "general",
  "summary": {
    "overall_assessment": "...",
    "primary_conversion_goal_guess": "Lead form submission",
    "top_strengths": ["..."],
    "top_risks": ["..."]
  },
  "issues": [...],
  "recommendations": [...],
  "quick_wins": [...]
}
```

У **`preset=craftum`** в корне JSON (и в сохранённом файле `--output`) есть, например:

```json
"craftum_block_plan": [
  {
    "block_type": "Отзывы",
    "goal": "Снять сомнения перед заявкой",
    "placement": "сразу после hero",
    "fields": ["Заголовок секции", "Имя", "Текст отзыва"],
    "content_example": "Марина: стало проще справляться с тревогой после первой сессии.",
    "style_guidance": "Тон спокойный, как в остальных текстах страницы; без пиксельных и CSS-советов.",
    "validation_check": "Под первым экраном видны минимум два отзыва с именами."
  }
]
```

При **`--output-format readable`** (или `--save-report` с тем же форматом) для `preset=craftum` в текст добавляется секция **«Рекомендуемые блоки для добавления»** (содержимое из `craftum_block_plan`). Если массив пуст, в этой секции будет краткое пояснение; для других пресетов отдельная секция не выводится.

## Baseline snapshot (`--baseline`)

**Контрольная точка «до изменений»** на диске: один запуск выполняет три независимых сценария для того же URL и складывает артефакты в каталог (по умолчанию `<AUDITS_DIR>/baseline`, см. `AUDITS_DIR` и `app.core.paths`). Дальше эту папку подхватывает **full-audit / compare** (см. следующий раздел).

**Что выполняется:**

1. Content-аудит с пресетом **`general`** → `content.json` + человекочитаемый **`content_readable.md`** (тот же markdown, что у CLI `--save-report` / `readable_export.build_landing_audit_readable_markdown`).
2. Аудит с пресетом **`craftum`** → `craftum.json`.
3. **Visual**-аудит → `visual.json`. При ошибке файл всё равно создаётся как JSON-заглушка (`baseline_status`, `error_message`, `error_type`); общий прогон не прерывается.

**Manifest:** `manifest.json` — `url`, `created_at` (UTC ISO), `modes_run`, `artifacts` (пути относительно корня проекта, если каталог внутри репозитория), `status` (`ok` | `partial` | `failed`), `limitations`, `notes`, `project_version`, опционально `git_commit` (best-effort `git rev-parse --short HEAD`), плюс `modes_detail` по каждому режиму.

**Запуск:**

```bash
python main.py --url "https://example.com/" --baseline
# свой каталог (относительный путь — от корня проекта):
python main.py --url "https://example.com/" --baseline --baseline-dir audits/my-baseline
```

Код выхода: **0**, если сохранён хотя бы один успешный режим или только **partial** (например, упал visual); **1**, если все три режима завершились с ошибкой (`failed`), либо при сбое оркестратора до записи manifest.

## Full-audit / compare к baseline (`--full-audit` / `--compare-baseline`)

Сравнивает **текущее состояние URL** с сохранённым baseline: заново гоняются content (`general`), craftum и visual для этого URL, затем строится эвристическое сравнение (issues, риски, missing blocks, scores из `diff_service`, visual issue counts), плюс человекочитаемый отчёт.

**Артефакты по умолчанию** в `<AUDITS_DIR>/compare` (или `--compare-dir`):

| Файл | Назначение |
|------|------------|
| `current_content.json` | Текущий content-аудит |
| `current_content_readable.md` | Readable для content |
| `current_craftum.json` | Текущий craftum (или заглушка при ошибке) |
| `current_visual.json` | Текущий visual или заглушка |
| `comparison.json` | Итог сравнения (`overall_change`, `changes`, `conversion_assessment`, `block_assessment`, …) |
| `comparison_readable.md` | Отчёт для человека |
| `manifest.json` | Метаданные прогона, ссылки на baseline и артефакты |

**Baseline:** те же требования, что при съёмке baseline: `manifest.json`, `content.json`, `craftum.json`, `visual.json` (допустима заглушка visual). Путь: `--baseline-dir` или по умолчанию `<AUDITS_DIR>/baseline`.

```bash
python main.py --url "https://example.com/" --full-audit
# синоним:
python main.py --url "https://example.com/" --compare-baseline
python main.py --url "https://example.com/" --full-audit --baseline-dir audits/baseline --compare-dir audits/full_audit
```

**Важно:** сравнение **не детерминированное LLM-зеркало** — используются устойчивые эвристики по полям JSON. Частичный сбой текущего visual/craftum даёт `status: partial` в `comparison.json`, но сравнение по content обычно всё равно создаётся.

**Код выхода:** **0** при успешной валидации baseline и завершённом content-прогоне; **1** если baseline битый/отсутствует или не удалось выполнить текущий content-аудит.

## Installation

```bash
python -m venv .venv
pip install -r requirements.txt
playwright install chromium
```

Последняя строка нужна для **скриншота** в режиме `--mode visual` (браузер Chromium для Playwright).

**Windows:** при выводе большого JSON в консоль `main.py` пытается переключить stdout/stderr на UTF-8; при проблемах с кодировкой полагайтесь на сохранённый файл `--output` или задайте `PYTHONIOENCODING=utf-8`.

## Setup

1. Скопируйте `.env.example` в `.env`
2. Укажите `OPENAI_API_KEY`

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
REQUEST_TIMEOUT=20
MAX_TEXT_CHARS=12000
DEFAULT_LANG=ru
```

## HTTP API (FastAPI)

Минимальный слой **без авторизации и БД**; повторяет пайплайн CLI через `app.services.audit_pipeline.run_landing_audit` (parse → OpenAI → нормализованный JSON). Фоновых задач и хранения данных нет.

**CORS:** переменная окружения `ALLOWED_ORIGINS` задаёт разрешённые origin для браузерного UI. По умолчанию — `*` (удобно для разработки). Для продакшена укажите список через запятую, например `http://localhost:5173,https://app.example.com`. При явном списке origin включается `Access-Control-Allow-Credentials` совместимо с Starlette (при `*` credentials отключены).

**Запуск:**

```bash
pip install -r requirements.txt
uvicorn app.interfaces.api:app --host 127.0.0.1 --port 8000
```

**Проверка живости (`GET /health`):**

```bash
curl -s http://127.0.0.1:8000/health
```

Ответ: `{"status":"ok"}`.

**Возможности API для UI (`GET /meta/capabilities`):**

Статический JSON с поддерживаемыми языками, целями переписи, **списком пресетов** и версией API — чтобы фронтенд не дублировал те же списки и мог строить формы/валидацию от одного источника правды на сервере.

```bash
curl -s http://127.0.0.1:8000/meta/capabilities
```

Пример фрагмента ответа: `"presets":["general","services","expert","course","leadgen","craftum"]`.

**Аудит (`POST /audit`):**

```bash
curl -s -X POST http://127.0.0.1:8000/audit -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\",\"task\":\"Increase signups\",\"lang\":\"en\",\"preset\":\"services\",\"rewrite\":[\"hero\",\"cta\"],\"debug\":false}"
```

С пресетом Craftum (в ответе может быть `craftum_block_plan`):

```bash
curl -s -X POST http://127.0.0.1:8000/audit -H "Content-Type: application/json" -d "{\"url\":\"https://example.com\",\"lang\":\"ru\",\"preset\":\"craftum\"}"
```

Тело JSON: `url` (обязателен), опционально `task`, `lang` (только `ru` или `en`; иначе `422`), `preset` (один из `general` \| `services` \| `expert` \| `course` \| `leadgen` \| **`craftum`**; по умолчанию `general`; неверное значение → `422`), `rewrite` (массив из `hero` \| `cta` \| `trust`; пустой массив `[]` — как без переписи), `debug` (по умолчанию `false`). Ответ — тот же объект, что и в full mode CLI (включая `rewrites`, `language`, `preset`; при `preset=craftum` — **`craftum_block_plan`** при наличии в ответе модели).

Ошибки домена: `400` (парсинг/загрузка), `502` (LLM), `500` (анализ/внутренняя). Тело ошибки — плоский JSON: `{"error":"<code>","message":"<text>"}` (без обёртки `detail`).

**Документация OpenAPI:** после запуска сервера откройте [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (Swagger UI) или [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

**CLI** по-прежнему основной способ: `python main.py ...`

## Architecture

- `parser` — fetch и парсинг HTML через requests + BeautifulSoup
- `audit_pipeline` — общий сценарий parse + LLM для CLI и API
- `analyzer` — валидация и нормализация LLM-ответа (в т.ч. `craftum_block_plan` для craftum)
- `llm provider` — вызов OpenAI, извлечение JSON
- `exporter` — сохранение JSON (full mode)
- `report_builder` — человекочитаемое представление (включая секцию рекомендуемых блоков для `preset=craftum`)
- `readable_export` — markdown-экспорт landing-отчёта (CLI, web UI, baseline `content_readable.md`)
- `baseline_runner` — оркестрация baseline-снимка (`--baseline`)
- `compare_heuristics` — эвристики сравнения baseline vs текущий отчёт
- `compare_runner` — full-audit: текущие аудиты + `comparison.json` / readable (`--full-audit`)
- `assignment_formatter` — 5 строк рекомендаций (assignment mode)
- `interfaces/api` — минимальный FastAPI (`GET /health`, `GET /meta/capabilities`, `POST /audit`, CORS)
- `core/lang` — нормализация кода языка (`normalize_lang`)
- `core/user_task` — санитизация `user_task` (`sanitize_user_task`)
- `core/prompts` — `build_task_context`, языковые правила и защита от injection в system prompt; для `craftum` — блоки CRAFTUM MODE и Craftum Block Planner
- `core/presets` — допустимые пресеты и `build_preset_addon` для фокуса аудита

## Troubleshooting

- Не срабатывает screenshot в `--mode visual` → выполните `playwright install chromium`.
- Ошибка импорта `playwright` → проверьте `pip install -r requirements.txt`.

## Limitations v1

- Основной парсинг: HTML snapshot only (no JS rendering).
- **Visual audit** (`--mode visual`): для усиленного анализа используется **опциональный screenshot** (PNG во временной директории ОС). Нужны **Playwright** и установленный **Chromium** (`playwright install chromium`). Без них или при ошибке съёмки — только текстовый visual-аудит (fallback).

## Roadmap

- UI
- Дополнительные улучшения вне текущего объёма v1 — по мере необходимости
