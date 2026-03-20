# Landing Audit CLI (MVP v1)

CLI-инструмент для аудита лендингов с фокусом на конверсию.

На вход:
- `--url` (URL лендинга)
- `--task` (контекст задачи пользователя)

На выход:
- JSON-отчет с полями:
  - `summary`
  - `issues`
  - `recommendations`
  - `quick_wins`

## Технологии

- Python 3.10+
- requests
- beautifulsoup4
- openai
- python-dotenv
- tenacity

## Установка

1. Создайте виртуальное окружение:
   - Windows (PowerShell):
     - `python -m venv .venv`
     - `.venv\Scripts\Activate.ps1`
2. Установите зависимости:
   - `pip install -r requirements.txt`

## Настройка .env

1. Скопируйте `.env.example` в `.env`
2. Заполните `OPENAI_API_KEY`

Пример:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
REQUEST_TIMEOUT=20
MAX_TEXT_CHARS=12000
```

## Запуск

Пример команды:

`python main.py --url "https://example.com" --task "Проверь конверсионные слабые места" --output "output/report.json"`

Если `--output` не указан, используется `output/report.json`.

## Структура проекта

```text
app/
  core/
    config.py
    models.py
    prompts.py
  interfaces/
    cli.py
  providers/
    llm.py
  services/
    analyzer.py
    exporter.py
    parser.py
main.py
requirements.txt
.env.example
.gitignore
README.md
```

## Архитектурная заметка

Архитектура разделена на слои (`interfaces`, `services`, `providers`, `core`) и готова к переходу на FastAPI + UI:
- CLI можно заменить/дополнить HTTP-интерфейсом
- бизнес-логика и LLM-провайдер уже вынесены в отдельные модули
