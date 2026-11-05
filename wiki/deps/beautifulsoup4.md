# beautifulsoup4

**Fallback-парсинг HTML в spider (основной путь — lxml).**

- **Связи:** [modules](../modules.md)
- **Код:** pyproject.toml → `[project].dependencies`
- **Источник:** pyproject.toml, импорты в коде
- **Обновлено:** 2026-11-05

## Зачем используется

Fallback-парсинг HTML в spider (основной путь — lxml).

## Ограничения и заметки

В `spider.py` унифицированный интерфейс: lxml — основной, bs4 — запасной.

## Где используется

[[modules]]

## Источник

`pyproject.toml` (раздел `dependencies`), grep импортов по `pentool/`
и `pro/`; коммит `cb11bfd`.
