# Landing AI Auditor (v1)

CLI tool for conversion-focused landing page audits. Can be used as:
- **Assignment mode** — учебное задание «Агент: Подсказки по редизайну лендинга»: принимает URL, выводит 5 рекомендаций
- **Full audit mode** — расширенный JSON-отчет для production-аудита

**Stack:** Python ≥ 3.10, requests, beautifulsoup4, openai, tenacity, python-dotenv.

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

### Debug (`--debug`)

Для диагностики **декодирования и извлечения текста** (ложные срабатывания про «кодировку»):

```bash
python main.py --url "https://example.com" --output output/report.json --debug
```

В каталоге `output/debug/<хост>/` сохраняются `raw.html` и `extracted_text.txt`; в лог пишутся `status_code`, выбранная кодировка, `header_encoding`, `apparent_encoding`, фрагмент чистого текста. В данных парсера (и в JSON при передаче в LLM) в `audit_meta` есть `visible_text_quality`, `quality_hint` и **`text_quality_score`** (0.0–1.0, грубая инженерная оценка чистоты извлечённого текста; дублируется полем `text_quality_score` у корня `parsed_landing`). Системный промпт явно учитывает `quality_hint`, чтобы не заявлять о битой кодировке при `good`.

### Пример JSON

Full mode добавляет поле `language` (effective lang) в JSON:

```json
{
  "language": "ru",
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

## Installation

```bash
python -m venv .venv
pip install -r requirements.txt
```

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

## Architecture

- `parser` — fetch и парсинг HTML через requests + BeautifulSoup
- `analyzer` — валидация и нормализация LLM-ответа
- `llm provider` — вызов OpenAI, извлечение JSON
- `exporter` — сохранение JSON (full mode)
- `assignment_formatter` — 5 строк рекомендаций (assignment mode)
- `core/lang` — нормализация кода языка (`normalize_lang`)
- `core/user_task` — санитизация `user_task` (`sanitize_user_task`)
- `core/prompts` — `build_task_context`, языковые правила и защита от injection в system prompt

## Limitations v1

- HTML snapshot only (no JS rendering)
- No visual layout analysis

## Roadmap

- FastAPI
- UI
- screenshot analysis
- device emulation
