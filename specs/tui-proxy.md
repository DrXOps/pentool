# Спецификация: ProxyScreen (TUI)

> Файл: `pentool/tui/screens/proxy/screen.py`
> Слой: `tui/`
> Зависит от: `api/proxy_api.py`, `storage/http_storage.py`
> Последнее обновление: 2026-03-25

---

## 1. Назначение

`ProxyScreen` — главный экран Proxy. Отображает историю HTTP-запросов (HTTP History), панель инспектора (запрос/ответ), управление перехватом. Реализован как `Widget` (не `Screen`) для монтирования в `ContentSwitcher`.

---

## 2. Зависимости

```
tui/screens/proxy/screen.py
  ← api/proxy_api.py         (ProxyAPI, InterceptedRequest)
  ← storage/http_storage.py  (HttpStorage — через app)
  ← tui/widgets/filter_bar.py
  ← tui/widgets/inspector_panel.py
  ← tui/widgets/resize_handle.py
  ← tui/widgets/context_menu.py
  textual_fastdatatable       (DataTable, ArrowBackend)
  pyarrow                     (pa.Table.from_pylist)
```

**НЕ импортирует из:** `modules/`.

---

## 3. Макет (layout)

```
┌──────────────────────────────────────────────────────────┐
│ [▶ Forward] [✕ Drop] [◉ Intercept OFF] [🔍 Filter]       │  ← Toolbar (id: toolbar)
├──────────────────────────────────────────────────────────┤
│ # │ Host          │ Method │ URL         │ Status │ Length│  ← DataTable (id: http-table)
│ 1 │ example.com   │ GET    │ /api/users  │ 200    │ 1234  │
│ 2 │ example.com   │ POST   │ /login      │ 302    │  0    │
│...│               │        │             │        │       │
├──── ResizeHandle (id: resize-table-detail) ──────────────┤
│ [Request]                │ [Response]                     │  ← Inspector (id: inspector)
│ GET /api/users HTTP/1.1  │ HTTP/1.1 200 OK               │
│ Host: example.com        │ Content-Type: application/json │
│                          │ {"users": [...]}               │
└──────────────────────────────────────────────────────────┘
   ↑ ResizeHandle (id: resize-req-resp, горизонтальный)
```

### Sub-вкладки (TabbedContent)
- **Intercept** — просмотр/редактирование ожидающих запросов
- **HTTP History** — таблица всех запросов (основная вкладка)
- **WS History** — WebSocket фреймы (заглушка)
- **Proxy Settings** — настройки прокси

---

## 4. Виджеты и ID

| ID | Виджет | Описание |
|----|--------|----------|
| `#toolbar` | `Horizontal` | Тулбар с кнопками |
| `#btn-forward` | `Button` | Переслать перехваченный запрос |
| `#btn-drop` | `Button` | Сбросить перехваченный запрос |
| `#btn-intercept` | `Button` | Toggle перехвата |
| `#http-table` | `DataTable` (fastdatatable) | Таблица HTTP History |
| `#resize-table-detail` | `ResizeHandle` | Вертикальный: между таблицей и инспектором |
| `#inspector` | `InspectorPanel` | Панель детали запроса/ответа |
| `#resize-req-resp` | `ResizeHandle` | Горизонтальный: между req и resp в инспекторе |
| `#filter-bar` | `FilterBar` | Строка быстрых фильтров |

**Правило:** все кнопки тулбара всегда присутствуют в DOM, скрываются через `display = False`.

---

## 5. Колонки таблицы

```python
_COL_LABELS = ["#", "Host", "Method", "URL", "Status", "Length", "Type"]
_col_names  = ["id", "host", "method", "url", "status_code", "length", "mime_type"]
```

Тип бэкенда: `ArrowBackend(pa.Table.from_pylist(rows))`.

Кэш строк: `_rows_cache: list[dict]` — для выбора строки по `cursor_row` индексу.

---

## 6. Ключевые методы

```python
def compose(self) -> ComposeResult
async def on_mount(self) -> None       # инициализация, загрузка истории

async def reload(self) -> None         # перезагрузить таблицу из HttpStorage
def _rows_to_arrow(self, rows: list[dict]) -> "pa.Table"

def on_data_table_row_selected(self, event) -> None    # показать детали в инспекторе
def on_data_table_header_selected(self, event) -> None # сортировка

def action_toggle_intercept(self) -> None
def action_forward(self) -> None
def action_drop(self) -> None
def action_toggle_inspector(self) -> None  # клавиша I

def on_mouse_down(self, event: MouseDown) -> None  # ContextMenu (Ctrl+клик / m)
```

---

## 7. События

| Событие | Источник | Обработчик | Действие |
|---------|---------|------------|---------|
| `ProxyAPI.on_new_request` callback | `ProxyServer` | `on_mount` регистрирует | `call_after_refresh(reload)` |
| `DataTable.RowSelected` | `#http-table` | `on_data_table_row_selected` | показать в `#inspector` |
| `DataTable.HeaderSelected` | `#http-table` | `on_data_table_header_selected` | сортировка |
| `Button.Pressed` `#btn-intercept` | тулбар | `action_toggle_intercept` | переключить перехват |
| `Key("i")` | глобально | `action_toggle_inspector` | скрыть/показать Inspector |
| `FilterBar.FilterChanged` | `#filter-bar` | `on_filter_bar_filter_changed` | перезагрузить с фильтром |

---

## 8. Контекстное меню (ContextMenu)

Открывается: `Ctrl+клик` (button=1+ctrl) или клавиша `m`.

Пункты меню:
- **Send to Repeater** — открыть запрос в новой вкладке Repeater
- **Send to Intruder** — открыть запрос в Intruder
- **Copy as curl** — скопировать как curl-команду (`utils/copy_as.py`)
- **Copy as Python** — скопировать как Python requests
- **Add annotation** — добавить заметку (`Ctrl+Enter`)
- **Delete** — удалить запись из HttpStorage

---

## 9. Сортировка

Паттерн textual-fastdatatable:
```python
def on_data_table_header_selected(self, event):
    col_name = self._col_names[event.column_index]
    self._sort_reverse = (self._sort_col == event.column_index) and not self._sort_reverse
    self._sort_col = event.column_index
    event.data_table.sort(by=col_name, reverse=self._sort_reverse)
    col = event.data_table.ordered_columns[event.column_index]
    col.label = Text(f"{col_name} {'▼' if self._sort_reverse else '▲'}")
    event.data_table._clear_caches()
    event.data_table.refresh()
```

---

## 10. Тест-кейсы

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | Монтирование в `ContentSwitcher` | нет ошибок |
| 2 | `#http-table` в DOM | `query_one("#http-table")` не бросает |
| 3 | `#btn-forward` в DOM | всегда присутствует |
| 4 | Выбор строки → инспектор обновился | `#inspector` показывает req/resp |
| 5 | Клик по заголовку "Status" → сортировка | строки отсортированы по status_code |
| 6 | Клавиша `I` → инспектор скрыт/показан | `inspector.display` меняется |
| 7 | Ctrl+клик → ContextMenu открыт | `ContextMenu` в DOM |
| 8 | ContextMenu "Send to Repeater" | RepeaterScreen получил запрос |
| 9 | `#btn-intercept` нажат → `Intercept ON` | `proxy_api.get_intercept() == True` |
| 10 | FilterBar: фильтр по host | таблица перезагружена с фильтром |

---

## 11. Известные баги

- FilterBar: фильтрация по Host и Status не работает (ошибка в ключах `get_metadata_batch`).
- Ctrl+F поиск не реализован.
- Выбор нескольких строк не реализован (Shift+Click / Ctrl+Click multi-select).
