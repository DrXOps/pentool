# Proxy — Документация модуля

## Статус: ✅ MVP — ручное тестирование пройдено

**Файлы:**
- `pentool/modules/proxy.py` — ядро: `ProxyServer`, `InterceptedRequest`, `MatchReplaceRule`
- `pentool/api/proxy_api.py` — публичный API слой (`ProxyAPI`)
- `pentool/tui/screens/proxy/screen.py` — TUI-экран (`ProxyScreen`)
- `pentool/tui/screens/proxy/screen.tcss` — стили
- `pentool/storage/http_storage.py` — SQLite-хранилище HTTP-истории

**Горячая клавиша:** `Shift+P`

---

## Назначение

HTTP/HTTPS MITM-прокси для перехвата, просмотра, модификации и пересылки трафика браузера. Поддерживает: перехват и редактирование запросов, Match/Replace правила, scope-фильтрацию, WS-историю. Аналог Burp Suite Proxy.

---

## Вкладки экрана (`#proxy-subtabs`)

### Intercept (`#tab-intercept`)
- Редактор `TextArea` (`#intercept-editor`) — редактирование перехваченного запроса
- Заголовки-preview (`#intercept-headers-preview`) над редактором
- Нижняя панель: **Sent Request** (`#intercept-sent-req`) + **Response** (`#intercept-resp-viewer`)
- Кнопки: `⏩ Forward` / `✖ Drop` — активны только при наличии перехваченного запроса
- Очередь: при нескольких перехваченных запросах показываются по одному, счётчик `(+N queued)`

### HTTP History (`#tab-http-history`)
- **FilterBar** (`#filter-bar`) — фильтрация по хосту, методу, статусу, scope
- **DataTable** (`#request-list`) — история: ID | Host | Method | URL | Status | Size | Time
- **ResizeHandle** вертикальный (`#resize-table-detail`) — разделитель таблица/детали
- **Request panel** (`#req-panel`) → `HttpView` (`#req-editor`)
- **Response panel** (`#resp-panel`) → `HttpView` (`#resp-viewer`)
- **ResizeHandle** горизонтальный (`#resize-req-resp`) — разделитель Request/Response
- **InspectorPanel** (`#inspector-panel`) — скрыт по умолчанию, открывается клавишей `I`

### WS History (`#tab-ws-history`)
- Таблица WebSocket-запросов с той же структурой что HTTP History
- Отдельные панели `#ws-req-editor` и `#ws-resp-viewer`

---

## Тулбар (`#toolbar`)

| Кнопка | ID | Действие |
|--------|----|----------|
| `○ Proxy` / `● Proxy:PORT` | `btn-proxy` | Запустить / остановить прокси-сервер |
| `○ Intercept` / `● Intercept` | `btn-intercept` | Включить / выключить режим перехвата |
| `Scope` | `btn-scope` | Открыть диалог настройки Scope |
| `M/R` | `btn-mr` | Открыть диалог Match & Replace |
| `Load History` | `btn-load-history` | Перезагрузить историю из БД |
| `Clear` | `btn-clear` | Очистить историю |

---

## Горячие клавиши

| Клавиша | Действие |
|---------|----------|
| `Ctrl+R` | Send to Repeater |
| `Ctrl+T` | Send to Target |
| `Ctrl+U` | Copy URL |
| `M` | Контекстное меню |
| `I` | Показать / скрыть Inspector |

---

## Контекстные меню

### Меню таблицы — DataTable (Ctrl+клик или `M`)
- Send to Repeater
- Send to Intruder
- Send to Scanner
- Send to Target
- Add/Remove to Scope
- Delete

### Меню текстовых панелей — Request/Response (Ctrl+клик)
- Copy / Select All
- Copy as curl / fetch() / ffuf / sqlmap / nmap / jwt_tool
- Open in Browser
- Save request.txt
- Send to Repeater

---

## Архитектура хранения

```
ProxyServer (in-memory)
  → on_request_done → ProxyScreen.update_request_row()
                       → HttpStorage (SQLite, таблица requests)
                       → DataTable (ArrowBackend)
```

- Таблица использует `textual_fastdatatable.DataTable` с `ArrowBackend(pa.Table.from_pylist(rows))`
- Новые запросы добавляются инкрементально через `_append_row_to_table()` (без полного reload)
- При фильтрах активных — полный reload через `_reload_table(filters)`
- Кэш строк: `_rows_cache: list[dict]` — синхронный доступ по `cursor_row`
- WebSocket-запросы фильтруются через `is_websocket=True/False`

---

## Публичный API

### `ProxyAPI`

```python
from pentool.api.proxy_api import ProxyAPI

api = ProxyAPI()

# Создать прокси-сервер
proxy = api.create_proxy(host="127.0.0.1", port=8080, cert_dir="/tmp/certs")

# Или инжектировать существующий
api.set_proxy(proxy_server)

# Состояние
api.is_running()        # bool
api.get_port()          # int
api.get_host()          # str
api.get_status()        # dict: running, host, port, intercept_enabled, scope,
                        #       requests_count, rules_count, waiting_count

# Перехват
api.set_intercept(True)
api.get_intercept()     # bool
api.forward(req_id, modified_raw=None)
api.drop(req_id)

# Запросы
reqs = api.get_requests(limit=100, method="GET", host="example.com")
req  = api.find_request(req_id)
api.clear_requests()

# Scope
api.set_scope(["example.com", "*.example.com"])
api.get_scope()         # list[str]

# Match/Replace
api.get_match_replace_rules()       # list[MatchReplaceRule]
api.set_match_replace_rules(rules)

# Коллбэки TUI
api.set_callbacks(
    on_new_request=lambda req: ...,
    on_request_done=lambda req: ...,
)

# Прямой доступ к ProxyServer
proxy = api.proxy  # property

# Проект
data = api.export_project_data()    # → dict: {proxy: {scope, match_replace}, http_history: [...]}
count, err = api.import_project_data(data)
```

### `ProxyScreen` — публичный API (вызывается из `app.py`)

```python
screen.add_request_row(req: InterceptedRequest) -> None      # новый запрос (без ответа)
screen.update_request_row(req: InterceptedRequest) -> None   # запрос завершён
screen.show_intercepted_request(req: InterceptedRequest) -> None  # показать в Intercept Tab
screen.show_intercept_response(req: InterceptedRequest) -> None   # показать ответ
screen.update_proxy_label(running: bool, port: int) -> None
screen.update_intercept_label(enabled: bool) -> None
screen.load_from_project() -> None   # перезагрузить таблицу после load_project()
```

### `InterceptedRequest`

```python
@dataclass
class InterceptedRequest:
    id: str                        # UUID
    method: str
    url: str
    headers: dict[str, str]
    body: str
    state: str                     # "waiting" | "forwarded" | "dropped"
    timestamp: datetime
    is_https: bool = False
    is_websocket: bool = False
    response: Optional[ParsedResponse] = None
```

---

## Известные проблемы / Исправленные баги

- **VTE / правая кнопка мыши**: `button=3` не доходит до Textual в VTE-терминале. Используется `Ctrl+клик` или клавиша `M`.
- **ResizeHandle**: `render()` → вертикальный `│` или горизонтальный `─`. Курсор меняется через ANSI escape (`\033[2 q` / `\033[0 q`). Импорт: `Leave`, `Enter` (не `MouseLeave`!).
- **Race condition**: `_update_and_reload` может прийти раньше чем `_store_request` завершился — решено через `_wait_for_row_id()` с sentinel `-1`.
- **WS History**: WebSocket-запросы фильтруются отдельно (`is_websocket=True`), не смешиваются с HTTP.
- **_ProxyDataTable**: Ctrl+клик публикует `ContextMenuRequest` через `post_message` — всегда поднимается к родителю.

---

## Чеклист ручного тестирования

### MVP ✅ (пройдено)
- [x] Нажать `○ Proxy` → кнопка меняется на `● Proxy:8080`, уведомление "Starting proxy on :8080"
- [x] Настроить браузер на прокси `127.0.0.1:8080`, открыть `http://example.com` — запрос в таблице
- [x] Выбрать запрос → в нижних панелях Request и Response
- [x] Клик по заголовку колонки → сортировка ▲/▼
- [x] Нажать `● Intercept` → запрос задерживается в браузере
- [x] В редакторе изменить заголовок, нажать `⏩ Forward` → запрос уходит модифицированным
- [x] Нажать `✖ Drop` → браузер получает 502
- [x] `Ctrl+R` → Repeater с запросом
- [x] `Ctrl+U` → URL скопирован
- [x] `M` / `Ctrl+клик` на строке → контекстное меню
- [x] Send to Scanner → Scanner открывается, URL в Target input
- [x] Add to Scope → FilterBar scope-toggle активен
- [x] Фильтр по хосту → таблица фильтруется
- [x] `I` → Inspector открывается/скрывается
- [x] Сохранить проект → открыть → история восстановлена

### DEMO (дополнительно)
- [ ] HTTPS: установить CA-сертификат (`Settings → Proxy → Install CA cert`), открыть `https://example.com` — перехватывается
- [ ] Match/Replace: правило `User-Agent: TestAgent` → проверить в перехваченном запросе
- [ ] Несколько запросов в очереди перехвата → показываются по одному, счётчик `(+N queued)`
- [ ] WS History: проксировать WebSocket-соединение → данные на вкладке WS History
- [ ] Copy as curl → вставить в терминал, запрос воспроизводится
- [ ] `Ctrl+клик` на Response → Copy as fetch() → корректный fetch() в буфере
- [ ] 200+ запросов — таблица не тормозит (ArrowBackend)
