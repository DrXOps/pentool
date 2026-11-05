# aiosqlite

**Асинхронный SQLite: история запросов, результаты интрудера, состояние вкладок.**

- **Связи:** [storage](../storage.md), [core](../core.md)
- **Код:** pyproject.toml → `[project].dependencies`
- **Источник:** pyproject.toml, импорты в коде
- **Обновлено:** 2026-11-05

## Зачем используется

Асинхронный SQLite: история запросов, результаты интрудера, состояние вкладок.

## Ограничения и заметки

Все операции требуют `await`; конкурентная запись даёт `database is locked` (см. [[storage]]).

## Где используется

[[storage]], [[core]]

## Источник

`pyproject.toml` (раздел `dependencies`), grep импортов по `pentool/`
и `pro/`; коммит `cb11bfd`.
