# Спецификация: Proxy (ядро)

> Файл: `pentool/modules/proxy.py`
> Слой: `modules/`
> Последнее обновление: 2026-03-25

---

## 1. Назначение

`ProxyServer` — HTTP/HTTPS перехватывающий прокси. Принимает соединения от браузера, применяет правила match/replace, опционально останавливает запрос для ручного просмотра (intercept mode), пересылает на целевой сервер и записывает трафик.

---

## 2. Зависимости

```
modules/proxy.py
  ← core/logging.py        (get_logger)
  ← utils/cert.py          (create_ssl_context_for_domain, load_or_create_ca)
  ← utils/http_client.py   (HTTPClient)
  ← utils/parser.py        (ParsedRequest, ParsedResponse, parse_http_request, ...)
```

**НЕ зависит от:** `tui/`, `api/`, `storage/`.

---

## 3. Публичный API

### Классы и типы

```python
@dataclass
class MatchReplaceRule:
    match: str
    replace: str
    target: Literal["request", "response", "both"] = "both"
    scope: Literal["headers", "body", "all"] = "all"
    is_regex: bool = False
    enabled: bool = True
    id: str  # auto UUID[:8]

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "MatchReplaceRule": ...

InterceptState = Literal["waiting", "forwarded", "dropped"]

@dataclass
class InterceptedRequest:
    id: str              # UUID
    method: str
    url: str
    headers: dict[str, str]
    body: str
    state: InterceptState
    timestamp: datetime
    response: Optional[ParsedResponse] = None
    _event: asyncio.Event  # внутренний — для ожидания решения
```

### ProxyServer

```python
class ProxyServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        cert_dir: Optional[str] = None,
        storage: Optional[HttpStorage] = None,
    ) -> None

    # Запуск/остановка
    async def start(self) -> None
    async def stop(self) -> None
    def is_running(self) -> bool

    # Состояние
    def get_status(self) -> dict  # см. ProxyAPI.get_status()

    # История (in-memory)
    @property
    def requests(self) -> list[InterceptedRequest]
    def get_requests(
        self,
        limit: int = 100,
        method: Optional[str] = None,
        host: Optional[str] = None,
    ) -> list[InterceptedRequest]
    def clear_requests(self) -> None

    # Перехват
    def forward(self, req_id: str, modified_raw: Optional[str] = None) -> None
    def drop(self, req_id: str) -> None

    # Конфигурация
    @property
    def intercept_enabled(self) -> bool
    @intercept_enabled.setter
    def intercept_enabled(self, value: bool) -> None

    @property
    def scope(self) -> list[str]
    def set_scope(self, hosts: list[str]) -> None
    def in_scope(self, url: str) -> bool

    @property
    def match_replace_rules(self) -> list[MatchReplaceRule]
    @match_replace_rules.setter
    def match_replace_rules(self, rules: list[MatchReplaceRule]) -> None

    # Коллбэки TUI
    on_new_request: Optional[Callable[[InterceptedRequest], None]]
    on_request_done: Optional[Callable[[InterceptedRequest], None]]
```

---

## 4. Поведение

### 4.1 HTTP-туннель (CONNECT)

1. Браузер шлёт `CONNECT host:443 HTTP/1.1`.
2. ProxyServer генерирует TLS-сертификат для домена (через `utils/cert.py`).
3. Отвечает `200 Connection established`.
4. Оба конца (браузер и сервер) переходят на TLS.
5. Далее — штатная обработка HTTP.

### 4.2 Match/Replace

Применяется к каждому запросу/ответу по порядку правил:
- `target="request"` → только к запросу
- `target="response"` → только к ответу
- `target="both"` → к обоим
- `scope="headers"` → только заголовки
- `scope="body"` → только тело
- `scope="all"` → и заголовки и тело
- `is_regex=True` → `re.sub(match, replace, text)`
- `enabled=False` → правило пропускается

### 4.3 Intercept mode

- `intercept_enabled=False` (по умолчанию): запросы проходят автоматически.
- `intercept_enabled=True`: ProxyServer ставит запрос в `state="waiting"`, вызывает `on_new_request(req)`, ждёт вызова `forward(req_id)` или `drop(req_id)` через `asyncio.Event`.
- Таймаут ожидания: `_INTERCEPT_TIMEOUT = 300.0` сек → автоматически forward.

### 4.4 Scope

- Пустой scope → все запросы записываются.
- Непустой scope → только запросы, чей хост совпадает с паттерном.
- Поддерживаются wildcards: `*.example.com`, `example.com`.

---

## 5. Взаимодействие с другими модулями

```
ProxyServer → HttpStorage.add_request()     (если storage передан)
ProxyServer → on_new_request callback       (TUI через ProxyAPI.set_callbacks)
ProxyServer → utils/cert.py                 (TLS-сертификаты)
ProxyServer → utils/http_client.py          (форвардинг запросов)
ProxyServer → utils/parser.py              (разбор HTTP)
```

---

## 6. Тест-кейсы

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | `start()` → `is_running()` | `True` |
| 2 | `stop()` → `is_running()` | `False` |
| 3 | HTTP-запрос через прокси | запись в `requests`, `state="forwarded"` |
| 4 | `intercept_enabled=True` → запрос ожидает → `forward()` | `state="forwarded"` |
| 5 | `intercept_enabled=True` → запрос ожидает → `drop()` | `state="dropped"` |
| 6 | `set_scope(["example.com"])` → запрос к `other.com` | не записывается |
| 7 | `MatchReplaceRule(match="X-Debug", replace="X-Debug: 1")` | заголовок добавлен |
| 8 | Regex replace: `match=r"token=\w+"`, `replace="token=REDACTED"` | тело изменено |
| 9 | HTTPS-запрос через CONNECT | успешно (с mock TLS) |
| 10 | `clear_requests()` | `requests` = `[]` |

---

## 7. Известные ограничения

- `on_new_request` callback вызывается из asyncio event loop — TUI должен быть thread-safe.
- CONNECT-туннель требует установленных CA-сертификатов в браузере.
- Максимальный размер тела: `_MAX_BODY = 10MB`.
- WebSocket-трафик: частичная поддержка (записывается как бинарные фреймы).
