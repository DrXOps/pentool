# Вики проекта Pentool

Точка входа. Агент открывает этот файл первым, чтобы не читать весь код.
Схема страниц и правила соответствия — в [CONTEXT](CONTEXT.md).

> **Статус:** Этап 2 starter kit (2026-11-05). Страницы модулей заполнены по
> коду; страницы зависимостей созданы. Существующая документация `docs/`
> **не перемещалась** — см. [CONTEXT](CONTEXT.md) → «Текущая документация».

## Модули

Корень кода — `pentool/` (в проекте нет `src/`); страница — `wiki/<module>.md`.

- [api](api.md) — фасады API поверх модулей
- [cli](cli.md) — CLI и headless-режим
- [collections](collections.md) — движок фильтрации таблиц
- [core](core.md) — конфиг, события, лицензии, плагины, БД-схема
- [export](export.md) — отчёты (HTML/Markdown/HackerOne/Bugcrowd/DefectDojo)
- [modules](modules.md) — доменные модули (intruder, repeater, decoder, …)
- [payloads](payloads.md) — YAML-наборы payload'ов
- [plugins](plugins.md) — загрузка плагинов
- [proxy](proxy.md) — прокси в отдельном процессе (демон + клиент)
- [services](services.md) — оркестрация и AI-интеграция
- [storage](storage.md) — SQLite-хранилища
- [tui](tui.md) — Textual-интерфейс и система вкладок
- [utils](utils.md) — HTTP-клиент, парсер, крипто, DNS, кэш

## Зависимости

- [textual](deps/textual.md), [textual-fastdatatable](deps/textual-fastdatatable.md)
- [aiohttp](deps/aiohttp.md), [aiosqlite](deps/aiosqlite.md)
- [lxml](deps/lxml.md), [beautifulsoup4](deps/beautifulsoup4.md)
- [pyarrow](deps/pyarrow.md), [rich](deps/rich.md)
- [click](deps/click.md), [cryptography](deps/cryptography.md)
- [pyyaml](deps/pyyaml.md), [psutil](deps/psutil.md), [pyperclip](deps/pyperclip.md)

## Концепции

- — (пусто: заполняется при разборе)

## Сущности

- — (пусто)

## Как пополнять

- Новый исходник — в `wiki/raw/` (неизменяемая зона), затем страницы в
  `concepts/`, `entities/` или `deps/` со ссылкой на него.
- Готовый промт: `prompts/karpathy-ingest.md`.
- Шаблон страницы: `wiki/_template.md`.

## Существующая документация (не мигрирована)

- `README.md`, `CONTRIBUTING.md`
- `docs/API_CONTRACTS.md` — контракты всех API-классов
- `docs/CI_CD.md`, `docs/INSTALLATION.md`, `docs/QUICKSTART.md`, `docs/USER_GUIDE.md`
- `docs/i18n/{en,ru,zh,hi}/` — переводы
- `docs/plan_tabs_repeater_intruder.md`, `docs/audit/README.md`
- `CLAUDE.md` — правила для агента

## AI-автоматизация (не модуль `pentool/`)

Каталог `ai/` — агентская обвязка, а не часть пакета: маршрутизация задач на
модели, эскалация, изоляция worktree, наблюдаемость.

- `ai/README.md` — как пользоваться, troubleshooting, как отключить
- `ai/discovery.md` — какие эндпоинты и модели реально доступны (проверено)
- `ai/models.yaml` — роли моделей и цепочки задач

Связано с [[CONTEXT]] (порог авто-сжатия, хуки `context-state.sh`) и
[[services]] (AI-интеграция в самом продукте). На код `pentool/` не влияет:
не импортируется им и не меняет его настройки.
