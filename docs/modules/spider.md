# Spider — Документация модуля

## Статус: ✅ MVP — ручное тестирование пройдено

**Файлы:**
- `pentool/modules/spider.py` — ядро: `AsyncSpider`, датаклассы результатов
- `pentool/tui/screens/spider/screen.py` — TUI-экран (`SpiderScreen`)
- `pentool/tui/screens/spider/screen.tcss` — стили
- `pentool/api/spider_api.py` — `SpiderAPI` (используется Scanner)

**Горячая клавиша:** `Shift+W`

---

## Назначение

Рекурсивный BFS-краулер сайта. Обходит страницы, собирает формы, API-эндпоинты, JS-файлы и URL-параметры. Результаты можно отправить в Scanner одной кнопкой. Аналог Burp Suite Spider/Crawler.

---

## Что собирает Spider

| Тип данных | Источник |
|-----------|---------|
| Страницы (URL) | `<a href>`, `<link>`, `<form action>`, `<script src>` |
| Формы | `<form>` → action, method, поля |
| API-эндпоинты | JS-файлы (10 regex-паттернов: fetch, axios, url=, endpoint=, ...) |
| GET-параметры | URL query string → `SpiderEndpoint.params` |
| JS-файлы | `<script src>` |
| Path-параметры | `/api/users/123` → числа/UUID в сегментах пути |
| data-атрибуты | `data-url`, `data-href`, `data-src`, `data-action`, `data-link` |
| meta refresh | `<meta http-equiv="refresh" content="0; url=...">` |
| robots.txt | `Disallow`/`Allow` → очередь краулинга + `Sitemap:` ссылки |
| sitemap.xml | `<loc>` → рекурсивно вложенные sitemap'ы |
| inline JS | `<script>` без src → regex-поиск URL |

---

## Компоненты TUI

### Тулбар (`#spider-toolbar`)
| Кнопка | ID | Действие |
|--------|----|----------|
| `🕷 Start` | `btn-spider-start` | Запустить краулер |
| `■ Stop` | `btn-spider-stop` | Остановить краулер |
| `⚡ Scan Found` | `btn-scan-found` | Отправить URL в Scanner |
| `🗑 Clear` | `btn-spider-clear` | Очистить результаты |

### Горячие клавиши
| Клавиша | Действие |
|---------|----------|
| `F5` | Start Spider |
| `F6` | Stop Spider |

### Конфигурация (`#config-panel`)
| Параметр | ID | По умолчанию |
|----------|----|-------------|
| Target URL | `#target-url` | пусто |
| Max depth | `#cfg-depth` | 3 |
| Max pages | `#cfg-pages` | 100 |
| Concurrency | `#cfg-concurrency` | 5 |
| Stay in scope | `#cfg-scope` | ✓ |
| Follow JS files | `#cfg-js` | ✓ |

### Прогресс (`#progress-area`)
- `ProgressBar` (`#spider-progress`) — обновляется в реальном времени
- `#progress-label` — `N / M`
- `#spider-hint` — `● IDLE` / `● RUNNING` (жёлтый)

### Вкладки результатов (`#spider-tabs`)

| Вкладка | ID | Содержимое |
|---------|----|-----------|
| 🗺 Site Map | `tab-sitemap` | `Tree` — иерархия страниц по директориям |
| 🔗 Endpoints | `tab-endpoints` | `RichLog` — API-эндпоинты с источником [HTML/JS/PARAM] и параметрами |
| 📋 Forms | `tab-forms` | `RichLog` — формы: action, method, поля |
| ⚡ JS Files | `tab-js` | `RichLog` — список JS-файлов |

---

## Датаклассы

```python
@dataclass
class FormField:
    name: str
    type: str = "text"
    value: str = ""

@dataclass
class SpiderForm:
    action: str
    method: str = "GET"
    fields: list[FormField]
    page_url: str = ""

@dataclass
class SpiderEndpoint:
    url: str
    source: str = "html"   # html | js | param | path | robots | sitemap | form
    method: str = "GET"
    params: list[str]
    body: str = ""          # для POST-форм
    headers: dict = {}

@dataclass
class SpiderResult:
    base_url: str
    pages: list[str]
    forms: list[SpiderForm]
    endpoints: list[SpiderEndpoint]
    js_files: list[str]
    errors: list[str]
    total_requests: int

    def to_dict(self) -> dict: ...
```

---

## Публичный API

### `AsyncSpider`

```python
from pentool.modules.spider import AsyncSpider

spider = AsyncSpider(
    max_depth=3,
    max_pages=100,
    concurrency=5,
    respect_scope=True,
    on_page=lambda url: print(f"Found: {url}"),      # коллбэк на каждую страницу
    on_progress=lambda done, total: print(f"{done}/{total}"),
)

result: SpiderResult = await spider.crawl("https://example.com")

print(len(result.pages))      # количество страниц
print(len(result.forms))      # количество форм
print(len(result.endpoints))  # API-эндпоинты
print(len(result.js_files))   # JS-файлы
print(len(result.errors))     # ошибки краулинга

# Остановить
spider.stop()
```

### `SpiderAPI` (используется Scanner)

```python
from pentool.api.spider_api import SpiderAPI

api = SpiderAPI.from_params(
    max_depth=3,
    max_pages=100,
    concurrency=5,
)
result = await api.crawl("https://example.com")
```

### `SpiderScreen` — публичный API

```python
# Запустить/остановить программно
screen.action_start_spider() -> None
screen.action_stop_spider() -> None
screen.action_clear_spider() -> None
```

---

## Интеграция со Scanner

Кнопка `⚡ Scan Found`:
1. Собирает все страницы (`result.pages`) + эндпоинты (`result.endpoints`)
2. Ограничивает до 50 URL
3. Переключает на Scanner (`action_switch_module("scanner")`)
4. Вставляет URL в `#target-input` (через перенос строки)

---

## Scope-фильтрация

При `respect_scope=True` (чекбокс `Stay in scope`):
- Краулер остаётся в пределах `base_domain` целевого URL
- Поддерживаются субдомены: `url.endswith(f".{base_domain}")`
- Поддомены типа `api.example.com` при цели `example.com` — в scope

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Spider (Shift+W) — экран отображается корректно
- [ ] Ввести `https://testphp.vulnweb.com`, нажать `🕷 Start`
- [ ] Indicator меняется на `● RUNNING` (жёлтый)
- [ ] Страницы появляются в Site Map в реальном времени
- [ ] ProgressBar и счётчик `N / M` обновляются
- [ ] По завершении — уведомление: `Spider done: N pages, N endpoints, N forms, N JS files`
- [ ] Вкладка Site Map: дерево страниц сгруппировано по директориям
- [ ] Вкладка Endpoints: список с источником `[HTML]` / `[JS]` / `[PARAM]`
- [ ] Вкладка Forms: формы с action, method и полями
- [ ] Вкладка JS Files: список JS-файлов с `⚡` иконкой
- [ ] `■ Stop` — краулер останавливается немедленно, UI возвращается в IDLE
- [ ] `⚡ Scan Found` → Scanner открывается, URL'ы вставлены в Target input
- [ ] `🗑 Clear` — все вкладки очищены, счётчики сброшены

### Конфигурация
- [ ] `Stay in scope` выключен → краулер уходит на внешние домены
- [ ] `Max depth=1` → обходит только страницы с главной
- [ ] `Max pages=5` → краулер останавливается после 5 страниц
- [ ] `Concurrency=1` → запросы последовательно (медленнее)
- [ ] URL без схемы (`testphp.vulnweb.com`) → автоматически добавляется `https://`

### DEMO (дополнительно)
- [ ] robots.txt: сайт с `Disallow` → запрещённые пути видны в Endpoints
- [ ] sitemap.xml: сайт с sitemap → страницы из sitemap добавлены в очередь
- [ ] JS-файлы: API-эндпоинты из `fetch('/api/users')` извлекаются в Endpoints вкладке
- [ ] Формы: POST-форма с полями → в Forms вкладке: action, fields перечислены
- [ ] Spider → Scan Found → Scanner запускает активный скан по найденным URL
