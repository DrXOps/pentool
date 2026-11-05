# utils

**Самый нижний слой: HTTP-клиент, парсер, кодирование, DNS, сертификаты, кэш.**

- **Связи:** [[core]], [[modules]], [[deps/aiohttp]], [[deps/lxml]]
- **Код:** pentool/utils/
- **Источник:** pentool/utils/*.py, tests/unit/utils/
- **Обновлено:** 2026-11-05

## Назначение

Утилиты без знания о домене. Правило слоёв жёсткое: **`utils` не импортирует
ничего из `pentool.*`** (кроме самого `utils`) — это гарантирует отсутствие
циклов.

Следствие: общая фабрика логгеров живёт здесь — `logging.py`
(`get_logger`, `_NamedLogger`). Если бы она осталась в [[core]], то
`utils/auth_login.py`, `utils/cert.py`, `utils/copy_as.py` нарушали бы
правило слоёв ради одной строки `get_logger(__name__)`. `pentool.core.logging`
реэкспортирует эти имена, поэтому импорты `from pentool.core.logging import
get_logger` остаются валидными.

## Публичный интерфейс

- `HTTPClient` (`http_client.py`) — асинхронный HTTP на `aiohttp`, с
  переопределением резолвера (DNS bypass).
- `ParsedRequest` / `ParsedResponse` (`parser.py`) — разбор и сборка
  HTTP-сообщений; `intercepted_request.py` — модель перехвата.
- `coder.py` — 19 encode/decode/hash-операций.
- `cert.py`, `certificate_transparency.py` — генерация CA и CT-логи.
- `dns_resolver.py`, `cdn_detector.py`, `scope.py` — резолвинг, обход CDN,
  управление scope.
- `diff.py`, `lru_cache.py`, `auth_headers.py`, `auth_login.py`,
  `copy_as.py`, `terminal_check.py`, `lightpanda.py`, `aiosql_daemon.py`.

## Инварианты и подводные камни

- `HTTPClient` принимает override-резолвер — используется для DNS bypass;
  не путать с системным резолвером.
- `LRUCache` потокобезопасен не по умолчанию — проверяйте вызовы из разных
  задач event loop.
- `ParsedRequest`/`ParsedResponse` — общий контракт между [[modules]],
  [[api]] и тестами; менять поля без миграции потребителей нельзя.

## Связи

Ни от чего не зависит внутри проекта. Является фундаментом для [[core]],
[[modules]], [[api]], [[tui]].

## Источник

Код `pentool/utils/*.py`; тесты `tests/unit/utils/`; коммит `cb11bfd`.
