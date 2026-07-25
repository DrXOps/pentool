# PENTOOL API CONTRACTS

**Версия:** 1.0  
**Цель:** Документация всех API-методов для разработчиков модулей и SaaS-интеграции

---

## СОДЕРЖАНИЕ

1. [ProxyAPI](#proxyapi)
2. [ScannerAPI](#scannerapi)
3. [IntruderAPI](#intruderapi)
4. [SpiderAPI](#spiderapi)
5. [RepeaterAPI](#repeaterapi)
6. [TargetAPI](#targetapi)
7. [DecoderAPI](#decoderapi)
8. [ComparerAPI](#comparerapi)
9. [SequencerAPI](#sequencerapi)

---

## ProxyAPI

**Файл:** `pentool/api/proxy_api.py`  
**Назначение:** Управление HTTP прокси-сервером

### Методы

#### `start(host: str, port: int) -> None`
Запустить прокси-сервер.

**Параметры:**
- `host` — адрес для прослушивания (обычно "127.0.0.1")
- `port` — порт (обычно 8080)

**Исключения:**
- `OSError` — если порт уже занят

**Пример:**
```python
from pentool.api.proxy_api import ProxyAPI

proxy = ProxyAPI()
await proxy.start("127.0.0.1", 8080)
```

---

#### `stop() -> None`
Остановить прокси-сервер.

**Пример:**
```python
await proxy.stop()
```

---

#### `is_running -> bool` (property)
Проверить, запущен ли прокси.

**Возвращает:** `True` если запущен, иначе `False`

**Пример:**
```python
if proxy.is_running:
    print("Proxy is running")
```

⚠️ **Важно:** Это property, вызывать БЕЗ скобок!

---

#### `get_requests(limit: int = 100) -> list[dict]`
Получить историю перехваченных запросов.

**Параметры:**
- `limit` — максимальное количество записей

**Возвращает:** Список словарей с полями:
- `id` (int)
- `method` (str)
- `url` (str)
- `status_code` (int)
- `timestamp` (float)
- `host` (str)
- `length` (int)

**Пример:**
```python
requests = await proxy.get_requests(limit=50)
for req in requests:
    print(f"{req['method']} {req['url']}")
```

---

#### `export_project_data() -> dict`
Экспортировать данные прокси для сохранения проекта.

**Возвращает:** Словарь с ключами:
- `requests` — список перехваченных запросов
- `match_replace_rules` — правила Match/Replace
- `scope` — настройки scope

**Пример:**
```python
data = await proxy.export_project_data()
# Сохранить в JSON
```

---

#### `import_project_data(data: dict) -> None`
Импортировать данные прокси из проекта.

**Параметры:**
- `data` — словарь, полученный из `export_project_data()`

**Пример:**
```python
await proxy.import_project_data(saved_data)
```

---

## ScannerAPI

**Файл:** `pentool/api/scanner_api.py`  
**Назначение:** Управление сканером уязвимостей

### Методы

#### `start_scan(targets: list[str], checks: list[str] | None = None) -> None`
Запустить сканирование.

**Параметры:**
- `targets` — список URL для сканирования
- `checks` — список имён checks (None = все)

**Пример:**
```python
from pentool.api.scanner_api import ScannerAPI

scanner = ScannerAPI()
await scanner.start_scan(
    targets=["https://example.com"],
    checks=["xss", "sqli", "ssti"]
)
```

---

#### `get_findings() -> list[Finding]`
Получить найденные уязвимости.

**Возвращает:** Список объектов `Finding` с полями:
- `severity` (str): "critical", "high", "medium", "low", "info"
- `title` (str)
- `url` (str)
- `description` (str)
- `evidence` (str)
- `confidence` (str): "certain", "firm", "tentative"

**Пример:**
```python
findings = scanner.get_findings()
for f in findings:
    print(f"{f.severity.upper()}: {f.title} at {f.url}")
```

---

#### `get_stats() -> dict`
Получить статистику сканирования.

**Возвращает:** Словарь:
- `total_findings` (int)
- `by_severity` (dict): подсчёт по критичности
- `scanned_urls` (int)
- `duration_seconds` (float)

---

## IntruderAPI

**Файл:** `pentool/api/intruder_api.py`  
**Назначение:** Управление атаками Intruder

### Типы данных

#### `AttackType` (Enum)
```python
class AttackType(str, Enum):
    SNIPER = "sniper"              # Один payload set, по очереди
    BATTERING_RAM = "battering_ram"  # Один payload set, во все позиции
    PITCHFORK = "pitchfork"        # N payload sets, синхронно
    CLUSTER_BOMB = "cluster_bomb"  # N payload sets, все комбинации
```

#### `IntruderConfig` (dataclass)
```python
@dataclass
class IntruderConfig:
    template: str           # Шаблон запроса с маркерами §§
    attack_type: AttackType
    payloads: list[list[str]]  # Один список на каждую позицию
    threads: int = 10
    delay_ms: int = 0
```

#### `IntruderResult` (dataclass)
```python
@dataclass
class IntruderResult:
    payload: str | tuple[str, ...]  # Один или несколько payloads
    status_code: int
    length: int
    response_time_ms: float
    response_body: str
```

### Методы

#### `start_attack(config: IntruderConfig) -> list[IntruderResult]`
Запустить атаку.

**Параметры:**
- `config` — конфигурация атаки

**Возвращает:** Список результатов

**Пример:**
```python
from pentool.api.intruder_api import IntruderAPI, IntruderConfig, AttackType

intruder = IntruderAPI()

config = IntruderConfig(
    template="GET /search?q=§payload§ HTTP/1.1\r\nHost: example.com\r\n\r\n",
    attack_type=AttackType.SNIPER,
    payloads=[["admin", "user", "test", "root"]],
    threads=5,
)

results = await intruder.start_attack(config)
for r in results:
    print(f"{r.payload}: {r.status_code} ({r.length} bytes)")
```

---

#### `pause() -> None`
Приостановить атаку.

#### `resume() -> None`
Возобновить атаку.

#### `stop() -> None`
Остановить атаку.

---

## SpiderAPI

**Файл:** `pentool/api/spider_api.py`  
**Назначение:** Краулинг веб-приложений

### Типы данных

#### `SpiderResult` (dataclass)
```python
@dataclass
class SpiderResult:
    pages: list[str]           # Найденные URL
    forms: list[FormData]      # Найденные формы
    endpoints: list[Endpoint]  # Найденные эндпоинты
    js_files: list[str]        # Найденные JS-файлы
```

### Методы

#### `crawl(base_url: str, max_depth: int = 3, max_pages: int = 100) -> SpiderResult`
Краулить сайт.

**Параметры:**
- `base_url` — начальный URL
- `max_depth` — максимальная глубина
- `max_pages` — максимум страниц

**Возвращает:** `SpiderResult`

**Пример:**
```python
from pentool.api.spider_api import SpiderAPI

spider = SpiderAPI()
result = await spider.crawl("https://example.com", max_depth=2)

print(f"Found {len(result.pages)} pages")
print(f"Found {len(result.forms)} forms")
```

---

## RepeaterAPI

**Файл:** `pentool/api/repeater_api.py`  
**Назначение:** Отправка модифицированных HTTP-запросов

### Методы

#### `send_request(raw_request: str) -> ParsedResponse`
Отправить HTTP-запрос.

**Параметры:**
- `raw_request` — полный HTTP-запрос (заголовки + тело)

**Возвращает:** `ParsedResponse` с полями:
- `status` (int)
- `headers` (dict)
- `body` (str)

**Пример:**
```python
from pentool.api.repeater_api import RepeaterAPI

repeater = RepeaterAPI()

request = """GET /api/users HTTP/1.1
Host: example.com
User-Agent: Pentool/1.0

"""

response = await repeater.send_request(request)
print(f"Status: {response.status}")
print(f"Body: {response.body}")
```

---

## TargetAPI

**Файл:** `pentool/api/target_api.py`  
**Назначение:** Управление site map

### Методы

#### `add_url(url: str) -> None`
Добавить URL в site map.

#### `add_request_from_proxy(request_id: int) -> None`
Добавить запрос из истории прокси в site map.

#### `get_site_map() -> dict`
Получить дерево site map.

**Возвращает:** Вложенный словарь вида:
```python
{
    "example.com": {
        "": ["/", "/about"],  # Корневая директория
        "api": ["/api/users", "/api/posts"],
        "admin": ["/admin/login"]
    }
}
```

---

## DecoderAPI

**Файл:** `pentool/api/decoder_api.py`  
**Назначение:** Кодирование/декодирование данных

### Методы

#### `encode(data: str, operation: str) -> str`
Закодировать данные.

**Параметры:**
- `data` — исходные данные
- `operation` — имя операции (см. список ниже)

**Возвращает:** Закодированная строка

**Поддерживаемые операции:**
- `"base64"` — Base64
- `"url"` — URL encoding
- `"html"` — HTML entities
- `"hex"` — Hex encoding
- `"rot13"` — ROT13
- `"md5"` — MD5 hash
- `"sha1"` — SHA1 hash
- `"sha256"` — SHA256 hash
- `"jwt_decode"` — JWT decode (без проверки подписи)
- ... (всего 19 операций)

**Пример:**
```python
from pentool.api.decoder_api import DecoderAPI

decoder = DecoderAPI()

encoded = decoder.encode("Hello World", "base64")
print(encoded)  # "SGVsbG8gV29ybGQ="

decoded = decoder.decode(encoded, "base64")
print(decoded)  # "Hello World"
```

---

## ComparerAPI

**Файл:** `pentool/api/comparer_api.py`  
**Назначение:** Сравнение текстов (diff)

### Методы

#### `compare(text1: str, text2: str, mode: str = "unified") -> str`
Сравнить два текста.

**Параметры:**
- `text1` — первый текст
- `text2` — второй текст
- `mode` — режим diff: "unified", "context", "html"

**Возвращает:** Diff в выбранном формате

**Пример:**
```python
from pentool.api.comparer_api import ComparerAPI

comparer = ComparerAPI()

diff = comparer.compare(
    "Hello World",
    "Hello Pentool",
    mode="unified"
)
print(diff)
```

---

## SequencerAPI

**Файл:** `pentool/api/sequencer_api.py`  
**Назначение:** Анализ энтропии токенов

### Методы

#### `analyze(tokens: list[str]) -> SequencerReport`
Проанализировать последовательность токенов.

**Параметры:**
- `tokens` — список токенов для анализа

**Возвращает:** `SequencerReport` с полями:
- `entropy` (float) — энтропия в битах
- `is_predictable` (bool) — предсказуема ли последовательность
- `patterns` (list[str]) — найденные паттерны

**Пример:**
```python
from pentool.api.sequencer_api import SequencerAPI

sequencer = SequencerAPI()

tokens = ["abc123", "abc124", "abc125", "abc126"]
report = sequencer.analyze(tokens)

print(f"Entropy: {report.entropy:.2f} bits")
print(f"Predictable: {report.is_predictable}")
```

---

## ОБЩИЕ ПРИНЦИПЫ

### 1. Асинхронность
Все методы, выполняющие I/O операции, являются `async` и должны вызываться с `await`:
```python
result = await api.method()  # ✅ Правильно
result = api.method()         # ❌ Неправильно
```

### 2. Обработка ошибок
API методы могут выбрасывать исключения:
- `ValueError` — некорректные параметры
- `RuntimeError` — ошибка во время выполнения
- `TimeoutError` — таймаут операции

Пример обработки:
```python
try:
    result = await scanner.start_scan(targets)
except ValueError as e:
    print(f"Invalid parameters: {e}")
except RuntimeError as e:
    print(f"Runtime error: {e}")
```

### 3. Type Hints
Все API методы аннотированы типами. Используйте mypy для проверки:
```bash
mypy pentool/api/
```

### 4. Import Paths
Всегда импортируйте из `pentool.api.*`, а не из `pentool.modules.*`:
```python
from pentool.api.scanner_api import ScannerAPI  # ✅ Правильно
from pentool.modules.scanner import Scanner    # ❌ Неправильно
```

---

## СОБЫТИЯ (EventBus)

API-методы могут генерировать события через `EventBus`. Подписаться можно так:

```python
from pentool.core.event_bus import get_event_bus
from pentool.core.events import FindingDiscovered

bus = get_event_bus()

def on_finding(event: FindingDiscovered):
    print(f"New finding: {event.finding.title}")

bus.subscribe(FindingDiscovered, on_finding)
```

### Основные события:

- `ProxyRequestDoneEvent` — перехвачен HTTP-запрос
- `FindingDiscovered` — найдена уязвимость
- `ScanStarted`, `ScanFinished` — сканирование начато/завершено
- `IntruderResultAdded`, `IntruderFinished` — результаты атаки
- `SpiderFinished`, `UrlCrawled` — краулинг

---

## ЛИЦЕНЗИРОВАНИЕ

Некоторые API-методы требуют лицензии. Проверка:

```python
from pentool.core.license import get_session_license

lic = get_session_license()

if lic.has_feature("scanner_extended"):
    # Запустить расширенные checks
    pass
else:
    print("Extended scanner requires PRO license")
```

Методы с ограничениями:
- `ScannerAPI.start_scan()` — расширенные checks требуют `scanner_extended`
- `IntruderAPI.start_attack()` — все типы атак требуют `intruder_all_types`
- Лимиты (threads, max_pages) берутся из `lic.get_limit()`

---

## ТЕСТИРОВАНИЕ API

Все API имеют unit-тесты в `tests/api/`:

```bash
pytest tests/api/test_scanner_api.py -v
pytest tests/api/test_intruder_api.py -v
```

Пример теста:
```python
import pytest
from pentool.api.scanner_api import ScannerAPI

@pytest.mark.asyncio
async def test_scanner_start():
    scanner = ScannerAPI()
    await scanner.start_scan(["https://httpbin.org"])
    findings = scanner.get_findings()
    assert isinstance(findings, list)
```

---

## CHANGELOG

### v1.0 (2026-07-22)
- Начальная версия контрактов
- Документация всех основных API
- Добавлен StorageInterface для SaaS-готовности

---

**Для разработчиков:** При добавлении новых методов в API, обязательно обновите этот документ!
