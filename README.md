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

## Assignment Mode

**Input:** URL лендинга  
**Output:** 5 кратких рекомендаций по редизайну (stdout, без JSON)

- Использует OpenAI для анализа
- Включает обработку ошибок и логирование
- Не сохраняет файлы; вывод только в консоль

### Запуск

```bash
python main.py --mode assignment --url "https://example.com"
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
python main.py --url "https://example.com" --task "Improve conversion"
python main.py --url "https://example.com" --task "Check CTA" --output output/report.json --verbose
```

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

## Limitations v1

- HTML snapshot only (no JS rendering)
- No visual layout analysis

## Roadmap

- FastAPI
- UI
- screenshot analysis
- device emulation
