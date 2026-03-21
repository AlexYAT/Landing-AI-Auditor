# Landing AI Auditor (v1)

CLI tool for conversion-focused landing page audits. Can be used as:
- **Assignment mode** — учебное задание «Агент: Подсказки по редизайну лендинга»: принимает URL, выводит 5 рекомендаций
- **Full audit mode** — расширенный JSON-отчет для production-аудита

**Stack:** Python ≥ 3.10, requests, beautifulsoup4, openai, tenacity, python-dotenv.

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

### Пример вывода

```
Improve clarity of the main value proposition
Strengthen call-to-action visibility and wording
Add trust elements near conversion points
Simplify page structure for better readability
Ensure consistent visual hierarchy
```

## Full Audit Mode

**Input:** URL + task (опционально)  
**Output:** Полный JSON-отчет в файл + stdout

### Запуск

```bash
python main.py --url "https://example.com" --task "Improve conversion"
python main.py --url "https://example.com" --task "Check CTA" --output output/report.json --verbose
```

### Пример JSON

```json
{
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
```

## Architecture

- `parser` — fetch и парсинг HTML через requests + BeautifulSoup
- `analyzer` — валидация и нормализация LLM-ответа
- `llm provider` — вызов OpenAI, извлечение JSON
- `exporter` — сохранение JSON (full mode)
- `assignment_formatter` — 5 строк рекомендаций (assignment mode)

## Limitations v1

- HTML snapshot only (no JS rendering)
- No visual layout analysis

## Roadmap

- FastAPI
- UI
- screenshot analysis
- device emulation
