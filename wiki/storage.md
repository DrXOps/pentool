# storage

**SQLite-хранилища: история HTTP, состояние интрудера, обработка крупных тел.**

- **Связи:** [[core]], [[modules]], [[api]]
- **Код:** pentool/storage/
- **Источник:** pentool/storage/*.py, tests/integration/test_http_storage.py
- **Обновлено:** 2026-11-05

## Назначение

Персистентный слой. Правило слоёв: `storage` не импортирует `modules`,
`tui`, `api`, `cli`. Схема создаётся `core.db_schema.init_db()`.

## Публичный интерфейс

- `BaseSqliteStorage` — общая реализация поверх `aiosqlite`.
- `HttpStorage` — история запросов/ответов прокси.
- `IntruderStorage` — результаты атак и сохранённое состояние вкладок
  (`save_state`/`load_state`/`delete_tab` по `tab_uid`).
- `intruder_models.IntruderResult` — value object результата. Живёт в
  `storage` (а не в [[modules]]), потому что `IntruderStorage` обязан его
  возвращать, а правило слоёв запрещает `storage → modules`.
  `pentool.modules.intruder` реэкспортирует имя — старые импорты, включая
  PRO-пакет `pro/`, валидны.
- `LargeBodyHandler` — вынос крупных тел из БД в отдельное хранилище.

## Инварианты и подводные камни

- **Один процесс, одно подключение.** Конкурентная запись даёт
  `database is locked` — исправлено в `SiteMap.save()` (`pentool/modules/target.py`)
  и закреплено тестом `test_target.py::test_save_and_load`.
- `aiosqlite` требует `await` на всех операциях; синхронный доступ блокирует
  event loop.
- `LargeBodyHandler` выносит тела, чтобы БД не распухала; читатели обязаны
  проверять, не вынесено ли тело.

## Связи

Зависит от [[core]] (схема, `StorageInterface`). Используется [[api]] и
[[modules]] (Repeater, Intruder, SiteMap).

## Источник

Код `pentool/storage/`; тесты `tests/integration/test_http_storage.py`;
коммит `cb11bfd`.
