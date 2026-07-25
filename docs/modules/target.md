# Target — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/modules/target.py` — ядро: `SiteMap`, `SiteNode`
- `pentool/api/target_api.py` — публичный API (`TargetAPI`)
- `pentool/tui/screens/target/screen.py` — TUI-экран (`TargetScreen`)
- `pentool/tui/screens/target/screen.tcss` — стили
- `tests/unit/modules/test_target.py` — 19 unit-тестов

**Горячая клавиша:** `Shift+T`

---

## Назначение

Древовидная карта сайта (Site Map), агрегирующая все обнаруженные хосты и пути. Автоматически пополняется из Proxy-трафика. Позволяет управлять scope, экспортировать в JSON и отправлять хосты в Scanner. Аналог Burp Suite Target/Site Map.

---

## Компоненты TUI

### Тулбар
| Кнопка | ID | Действие |
|--------|----|----------|
| `★ Add to Scope` | `btn-add-scope` | Добавить выбранный хост в scope |
| `✖ Remove from Scope` | `btn-remove-scope` | Убрать из scope |
| `↺ Reload from DB` | `btn-refresh` | Перезагрузить карту из SQLite |
| `🗑 Clear` | `btn-clear` | Очистить карту |
| `📄 Export JSON` | `btn-export` | Экспортировать в JSON-файл |

### Горячие клавиши
| Клавиша | Действие |
|---------|----------|
| `M` | Контекстное меню для выбранного узла |
| `Ctrl+клик` / ПКМ | Контекстное меню |

### Дерево (`#site-tree`)
```
Site Map (N hosts)
  ├─ ★ example.com (in scope) (42)   ← зелёный, жирный
  │    ├─ /  [GET] (15)
  │    ├─ /login  [GET POST] (8)
  │    └─ /api/users  [GET POST PUT] (19)
  └─ other.com (3)
       └─ /  [GET] (3)
```

- Хосты в scope: `★` зелёный жирный + `(in scope)`
- В скобках — количество запросов
- Лист-узел показывает путь + HTTP-методы + количество запросов

### Detail Panel (`#detail-panel`)
`RichLog` — при выборе узла отображает:

**Хост:**
- `host`, `In scope: YES/NO`, `Endpoints: N`, `Total requests: N`, первые 20 путей

**Путь:**
- `host/path`, `Methods: GET, POST`, `Requests: N`, `Last seen: YYYY-MM-DD HH:MM`, `In scope: YES/NO`

---

## Контекстное меню

Появляется при `M` или `Ctrl+клик` на узле дерева:
- `🔍 Send to Scanner: hostname` → `SendHostToScanner` event → Scanner открывается с URL хоста
- `★ Add to Scope`
- `✖ Remove from Scope`

---

## Датаклассы

```python
@dataclass
class SiteNode:
    host: str
    path: str
    methods: set[str]           # {"GET", "POST"}
    request_count: int = 0
    last_seen: datetime
    in_scope: bool = False
    params: set[str]            # GET-параметры

    @classmethod
    def from_dict(cls, d: dict) -> "SiteNode": ...

class SiteMap:
    def add_request(self, req: ParsedRequest) -> None: ...
    def get_tree(self) -> dict[str, list[SiteNode]]: ...
    def get_hosts(self) -> list[str]: ...
    def get_paths(self, host: str) -> list[SiteNode]: ...
    def is_in_scope(self, host: str) -> bool: ...
    def set_in_scope(self, host: str, in_scope: bool) -> None: ...
    def get_scope(self) -> list[str]: ...  # хосты в scope
    def clear(self) -> None: ...
    def export_json(self) -> dict: ...    # {host: [node_dict, ...]}
    async def load(self) -> None: ...     # загрузить из SQLite
    async def save(self) -> None: ...     # сохранить в SQLite
```

---

## Публичный API

### `TargetAPI`

```python
from pentool.api.target_api import TargetAPI

api = TargetAPI(db_path="pentool.db")

# Загрузить из БД
await api.load()

# Добавить запрос (из Proxy)
from pentool.utils.parser import ParsedRequest
req = ParsedRequest(method="GET", url="https://example.com/login", headers={}, body="")
api.add_request(req)

# Дерево для TUI
tree: dict[str, list[SiteNode]] = await api.get_tree()

# Хосты и пути
hosts: list[str] = api.get_hosts()
paths: list[SiteNode] = api.get_paths("example.com")

# Scope
await api.set_in_scope("example.com", True)
scope: list[str] = await api.get_scope()

# Очистка
await api.clear()

# Экспорт
await api.export_json("/tmp/sitemap.json")

# Проект
data = api.export_project_data()    # → {"sitemap": {host: [node_dict, ...]}}
count = api.import_project_data(data)
```

### `TargetScreen` — публичный API (вызывается из `app.py`)

```python
# Добавить запрос из прокси (вызывается из ProxyScreen / ScannerScreen)
screen.add_request_from_proxy(req: ParsedRequest) -> None

# Обновить scope хоста (синхронизация из ProxyScreen)
screen.update_host_scope(host: str, in_scope: bool) -> None
```

---

## Интеграция с другими модулями

| Источник | Событие/вызов | Результат |
|---------|--------------|----------|
| Proxy `on_request_done` | `TargetAPI.add_request(req)` | Новый узел в дереве |
| Proxy контекстное меню | `SyncScopeToTarget(host, in_scope)` | Обновляется scope в дереве |
| Scanner `_send_url_to_target` | `target.add_request_from_proxy(req)` | URL из краулинга добавляется |
| Target контекстное меню | `SendHostToScanner(host)` | Scanner открывается с хостом |
| Proxy `add_scope` / `remove_scope` | `SyncScopeToTarget` message | Дерево обновляет иконки scope |

---

## Сохранение проекта

- `export_project_data()` → сериализует все `SiteNode` по хостам
- `import_project_data(data)` → восстанавливает дерево из `SiteNode.from_dict()`
- При reload (`↺ Reload from DB`) — scope-хосты сохраняются перед reload и восстанавливаются после

---

## Известные проблемы

- Данные не загружаются автоматически при монтировании: `on_mount` — `pass`. Требуется нажать `↺ Reload from DB` или отправить запрос из Proxy.
- `TargetAPI` инициализируется лениво при первом обращении через `_get_api()`.

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Target (Shift+T) — пустое дерево `Site Map (0 hosts)`
- [ ] Запустить Proxy, пропустить запрос к `http://example.com` → хост появляется в дереве автоматически
- [ ] Дерево: `example.com (1)` → раскрыть → `/  [GET] (1)`
- [ ] Несколько запросов к разным путям → дерево пополняется: `/login [GET POST] (3)`
- [ ] Нажать `↺ Reload from DB` → дерево перезагружается из БД
- [ ] Выбрать хост в дереве → Detail panel: хост, In scope: NO, Endpoints: N, Total requests: N
- [ ] Выбрать путь → Detail panel: path, Methods, Requests, Last seen
- [ ] `★ Add to Scope` на выбранном хосте → хост становится зелёным со звёздочкой
- [ ] `✖ Remove from Scope` → хост возвращается к обычному виду
- [ ] `M` на хосте → контекстное меню: Send to Scanner / Add Scope / Remove Scope
- [ ] Send to Scanner → Scanner открывается, URL хоста в Target input
- [ ] `📄 Export JSON` → диалог → файл сохраняется с корректной структурой `{host: [...]}`
- [ ] `🗑 Clear` → дерево пустое

### Интеграция со Scanner
- [ ] Scanner краулит `https://example.com/login` → путь `/login` появляется в Target
- [ ] Target → Send to Scanner → Scanner запускает скан по `https://example.com`

### Проект
- [ ] Сохранить проект → открыть снова → дерево восстановлено
- [ ] Scope восстанавливается (хосты помечены ★)

### DEMO (дополнительно)
- [ ] 10+ хостов в дереве → прокрутка работает
- [ ] Путь с GET-параметрами: `/search?q=test&page=1` → параметры видны в Detail panel
- [ ] Ctrl+клик на хосте → контекстное меню в позиции курсора
