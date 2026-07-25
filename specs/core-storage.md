# Спецификация: HttpStorage (хранилище HTTP-трафика)

> Файлы: `pentool/storage/http_storage.py`, `lru_cache.py`, `large_body_handler.py`
> Слой: `storage/`
> Последнее обновление: 2026-03-25

---

## 1. Назначение

`HttpStorage` — асинхронное SQLite-хранилище для HTTP-запросов и ответов, перехваченных прокси. Поддерживает полнотекстовый поиск (FTS5), WAL-режим для конкурентного доступа, LRU-кэш для горячих записей и вынос больших тел в файловую систему.

---

## 2. Зависимости

```
storage/http_storage.py
  ← core/config.py   (пути к БД и storage)
  ← core/logging.py  (get_logger)
  aiosqlite           (async SQLite)
```

**НЕ зависит от:** `modules/`, `tui/`, `api/`.

---

## 3. Схема БД

```sql
CREATE TABLE requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         REAL    NOT NULL,          -- unix timestamp
    host              TEXT    NOT NULL DEFAULT '',
    method            TEXT    NOT NULL DEFAULT '',
    url               TEXT    NOT NULL DEFAULT '',
    has_params        INTEGER NOT NULL DEFAULT 0, -- 1 если есть query params
    edited            INTEGER NOT NULL DEFAULT 0, -- 1 если изменён интруктором
    status_code       INTEGER,
    length            INTEGER,                    -- длина response body
    mime_type         TEXT,
    extension         TEXT,                       -- .json, .html, ...
    request_headers   TEXT,                       -- JSON
    response_headers  TEXT,                       -- JSON
    request_body      TEXT,
    response_body     TEXT,
    request_body_ref  TEXT,                       -- путь к файлу (>1MB)
    response_body_ref TEXT                        -- путь к файлу (>1MB)
);

-- FTS5 виртуальная таблица для полнотекстового поиска
CREATE VIRTUAL TABLE requests_fts USING fts5(
    url, host, request_body, response_body,
    content='requests', content_rowid='id'
);
```

Индексы: `idx_host`, `idx_status`, `idx_ts`, `idx_method`.
Триггеры: `requests_ai` (INSERT), `requests_ad` (DELETE), `requests_au` (UPDATE) — синхронизируют FTS5.

---

## 4. Публичный API

### Жизненный цикл

```python
storage = HttpStorage()
await storage.init_db("~/.config/pentool/history.db")
# ... работа ...
await storage.close()
```

### Методы

```python
async def init_db(self, db_path: str) -> None
```
Открыть БД, создать таблицы (DDL), включить WAL.

```python
async def close(self) -> None
```
Закрыть соединение с БД.

```python
async def add_request(
    self,
    request: ParsedRequest,
    response: Optional[ParsedResponse] = None,
    edited: bool = False,
) -> int
```
Добавить запись. Вернуть `id` строки. Тела >1MB выносятся в файлы (LargeBodyHandler).

```python
async def get_request(self, row_id: int) -> Optional[dict]
```
Получить полную запись по ID (включая тела, читает из файлов если нужно).

```python
async def get_metadata_batch(
    self,
    limit: int = 500,
    offset: int = 0,
    host: Optional[str] = None,
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    search: Optional[str] = None,  # FTS5 поиск
) -> list[dict]
```
Получить пакет метаданных (без тел) для таблицы HTTP History. Возвращает поля: `id, timestamp, host, method, url, has_params, edited, status_code, length, mime_type, extension`.

```python
async def delete_request(self, row_id: int) -> None
async def clear_all(self) -> None
async def count(self) -> int
```

```python
async def search_fts(self, query: str, limit: int = 100) -> list[dict]
```
Полнотекстовый поиск через FTS5. `query` — стандартный FTS5 синтаксис.

---

## 5. LRUCache (`storage/lru_cache.py`)

```python
class LRUCache:
    def __init__(self, capacity: int = 1000) -> None
    def get(self, key: int) -> Optional[dict]
    def put(self, key: int, value: dict) -> None
    def invalidate(self, key: int) -> None
    def clear(self) -> None
```

Используется внутри `HttpStorage` для кэширования горячих записей `get_request()`.

---

## 6. LargeBodyHandler (`storage/large_body_handler.py`)

```python
LARGE_BODY_THRESHOLD = 1 * 1024 * 1024  # 1 МБ

class LargeBodyHandler:
    def __init__(self, storage_dir: str) -> None
    def write(self, body: str, row_id: int, suffix: str) -> str  # путь к файлу
    def read(self, file_path: str) -> str
    def delete(self, file_path: str) -> None
```

Тела >1MB сохраняются как `{storage_dir}/{row_id}_{suffix}.body`. В БД — путь к файлу в поле `*_body_ref`.

---

## 7. Взаимодействие

```
HttpStorage ← ProxyServer.storage       (add_request при каждом запросе)
HttpStorage ← ProxyScreen.reload()      (get_metadata_batch для таблицы)
HttpStorage ← ProxyScreen.on_row_select (get_request для деталей)
HttpStorage ← SearchBar                 (search_fts)
```

---

## 8. Тест-кейсы

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | `init_db()` → таблицы созданы | `COUNT(*) = 0` |
| 2 | `add_request(req)` | вернуть `id > 0` |
| 3 | `add_request(req, resp)` → `get_request(id)` | все поля совпадают |
| 4 | `get_metadata_batch(host="example.com")` | только matching |
| 5 | `get_metadata_batch(method="POST")` | только POST |
| 6 | `get_metadata_batch(status_code=404)` | только 404 |
| 7 | `search_fts("password")` | найдены записи с "password" в URL/body |
| 8 | Тело >1MB → `add_request()` | `response_body_ref` не NULL, `response_body` NULL |
| 9 | `delete_request(id)` | FTS5 обновлена (не находится при поиске) |
| 10 | `clear_all()` → `count()` | `0` |
| 11 | Конкурентный доступ (WAL) | нет deadlock |
| 12 | LRUCache: повторный `get_request()` | из кэша (без SQL) |

---

## 9. Известные ограничения

- FTS5 не поддерживает поиск по части слова (нужен `MATCH "word*"`).
- WAL-файл растёт без checkpoint — нужна периодическая `PRAGMA wal_checkpoint(TRUNCATE)`.
- Большие тела не удаляются автоматически при `delete_request()` — нужен GC.
