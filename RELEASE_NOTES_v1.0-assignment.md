# Release v1.0-assignment

Версия для сдачи учебного проекта **«Агент: Подсказки по редизайну лендинга»**.

## Режимы работы

| Режим       | Input        | Output                    |
|-------------|--------------|---------------------------|
| **assignment** | URL          | 5 строк рекомендаций      |
| **full**       | URL + task   | Расширенный JSON audit    |

## Ключевые возможности

- HTML parsing (requests + BeautifulSoup)
- Анализ через OpenAI
- Retry и обработка ошибок (tenacity)
- Логирование
- Конфигурация через .env

## Ограничения

- No JS rendering
- No screenshot / visual analysis

## Пример запуска

```bash
python main.py --mode assignment --url "https://example.com"
```
