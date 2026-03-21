# Test Report v1.0-assignment

## Окружение

- **Python:** 3.12.10
- **ОС:** Windows
- **Примечание:** HTTPS-сайты (example.com) блокируются из-за SSL-сертификатов (environment issue на Windows)

---

## A. Smoke tests

| # | Тест | Команда | Статус | Комментарий |
|---|------|---------|--------|-------------|
| A1 | `--help` | `python main.py --help` | PASS | Справка выводится |
| A2 | Аргумент `--mode` | - | PASS | `--mode {full,assignment}` присутствует |
| A3 | Режимы full и assignment | - | PASS | Оба варианта в choices |

---

## B. Assignment mode

| # | URL | Команда | Статус | Комментарий |
|---|-----|---------|--------|-------------|
| B1 | http://httpbin.org/html | `python main.py --mode assignment --url "http://httpbin.org/html"` | PASS | 5 строк, не JSON, рекомендации связаны с содержанием (Moby-Dick, структура текста) |
| B2 | http://info.cern.ch | `python main.py --mode assignment --url "http://info.cern.ch"` | PASS | 5 строк, не JSON, рекомендации связаны с CERN / первой страницей |
| B3 | https://example.com | `python main.py --mode assignment --url "https://example.com"` | SKIP | **Environment issue:** SSL certificate verification failed (Windows) |

**Проверки:** программа не падает, в stdout ровно 5 строк, формат не JSON, рекомендации соответствуют контенту страницы.

---

## C. Full mode

| # | URL | Команда | Статус | Комментарий |
|---|-----|---------|--------|-------------|
| C1 | http://httpbin.org/html | `python main.py --mode full --url "http://httpbin.org/html" --task "Check"` | PASS | JSON выводится, файл `output/report.json` создан |

**Структура отчета:** `summary`, `issues`, `recommendations`, `quick_wins` — ключи соответствуют ожиданиям. `summary` содержит `overall_assessment`, `primary_conversion_goal_guess`, `top_strengths`, `top_risks`.

---

## D. Negative tests

| # | Случай | Команда | Статус | Комментарий |
|---|--------|---------|--------|-------------|
| D1 | Некорректный URL | `python main.py --url "not-a-url" --task "x"` | PASS | Сообщение об ошибке, без traceback, exit code 1 |
| D2 | Несуществующий домен | `python main.py --mode assignment --url "https://nonexistent-domain-xyz-12345.invalid"` | PASS | Сообщение об ошибке, без traceback, exit code 1 |
| D3 | Non-HTML resource | `python main.py --mode assignment --url "http://httpbin.org/image/png"` | PASS | `Error: Unsupported content type 'image/png'. Expected HTML page.` — понятная ошибка, exit code 1 |

**Проверки:** понятная ошибка, без traceback, завершение контролируемое.

---

## Сводка

| Категория | PASS | FAIL | SKIP |
|-----------|------|------|------|
| A. Smoke | 3 | 0 | 0 |
| B. Assignment | 2 | 0 | 1 (env) |
| C. Full | 1 | 0 | 0 |
| D. Negative | 3 | 0 | 0 |
| **Итого** | **9** | **0** | **1** |

## Вывод

Версия v1.0-assignment успешно прошла тесты в доступном окружении. Assignment mode выдает 5 строк рекомендаций, full mode — полный JSON-отчет. Обработка ошибок работает корректно. Тест на example.com пропущен из-за ограничений SSL в Windows.
