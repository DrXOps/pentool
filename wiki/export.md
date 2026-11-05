# export

**Генерация отчётов о находках в форматах интеграций: HTML, Markdown, HackerOne, Bugcrowd, DefectDojo.**

- **Связи:** [[api]], [[modules]]
- **Код:** pentool/export/
- **Источник:** pentool/export/__init__.py (архитектурный docstring)
- **Обновлено:** 2026-11-05

## Назначение

Нормализует находки сканера и превращает их в артефакты для внешних систем.
Часть экспортёров — PRO-функциональность.

## Публичный интерфейс

- `FindingData` — одна уязвимость (нормализована из `scanner_api.Finding`).
- `ReportData` — полный отчёт: цель, сводка, список находок.
- `BaseExporter` — ABC: `ReportData → str/bytes`.
- Реализации: `MarkdownExporter`, `HtmlExporter` (FREE);
  `ProHtmlExporter`, `HackerOneExporter`, `BugcrowdExporter`,
  `DefectDojoExporter` (PRO).

## Инварианты и подводные камни

- `MarkdownExporter` участвовал в цикле импортов (исправлено в `d7a96a3`) —
  не тяните UI-зависимости в экспортёры.
- PRO-экспортёры должны корректно отсутствовать на free-плане: фабрика
  выбирает доступную реализацию.

## Связи

Читает `FindingData` из [[api]]; связан с [[modules]] (источник находок).

## Источник

Docstring `pentool/export/__init__.py`, код `export/*.py`;
коммит `d7a96a3` (фикс циклического импорта).
