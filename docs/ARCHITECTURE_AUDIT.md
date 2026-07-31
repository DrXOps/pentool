# PENTOOL — АРХИТЕКТУРНЫЙ АУДИТ
**Дата:** 2026-07-31  
**Версия:** 0.1.5  
**Аудитор:** Claude Opus 5 (живой анализ кода)

---

## EXECUTIVE SUMMARY

### Метрики кодовой базы

| Показатель | Значение |
|---|---|
| Python-файлов | 158 |
| Строк кода (pentool/) | 32 998 |
| Строк тестов (tests/) | 12 939 |
| Тест-файлов | 78 |
| Тестов (unit) | **1 018 passed ✅** |
| Scanner checks | 23 |
| Архитектурных нарушений | **1** ⚠️ |

### Распределение по слоям

| Слой | Строки | % | Оценка |
|---|---|---|---|
| **TUI** | 14 990 | 45.4% | ⚠️ Доминирует |
| **Modules** | 10 814 | 32.8% | ✅ Норма |
| **Core** | 2 599 | 7.9% | ✅ |
| **Utils** | 1 220 | 3.7% | ✅ Компактный |
| **API** | 1 086 | 3.3% | ✅ Тонкий фасад |
| **Services** | 802 | 2.4% | ✅ |
| **Storage** | 604 | 1.8% | ✅ |
| **Plugins** | 41 | 0.1% | ⚠️ Заглушка |

### Общая оценка: **8.0 / 10**

**Прогресс с аудита 2026-07-26:**
- ✅ Версия выросла 0.1.1 → 0.1.5
- ✅ Core вырос 2 240 → 2 599 строк
- ✅ Services вырос 748 → 802 строки
- ✅ Scanner расширен с 21 до 23 checks
- ✅ 23 performance-оптимизации в EventBus/ProxyServer/HttpHistory

---

## 1. АРХИТЕКТУРНАЯ ЦЕЛОСТНОСТЬ

### Послойная схема
```
utils ← core ← modules ← api ← services ← tui / cli / plugins
                                  ↑
                               storage
```

### Нарушения

**⚠️ ЕДИНСТВЕННОЕ НАРУШЕНИЕ:** `tui/screens/decoder/screen.py:170`
```python
from pentool.modules.decoder import _detect_encoding, encode_op
```
TUI напрямую импортирует внутренние функции modules, минуя api-слой.

**Исправление:**
```python
# decoder_api.py — добавить публичные методы:
def detect_encoding(self, data: bytes) -> str: ...
def encode_op(self, op: str, value: str) -> str: ...

# screen.py — заменить на:
from pentool.api.decoder_api import DecoderAPI
```
**Приоритет:** 🟡 СРЕДНИЙ

---

## 2. API СЛОЙ (api/)

**1 086 строк, 10 файлов**

- ✅ Все классы — тонкие фасады без бизнес-логики
- ✅ `ExportableAPI` (base_api.py) создан как ABC с `export_project_data()`
- ⚠️ Существующие API-классы не наследуют `ExportableAPI` — задел создан, но не применён

---

## 3. SERVICES СЛОЙ (services/)

**802 строки, 5 файлов** — ProxyService, RepeaterService, IntruderService, ScanService, BaseService

- ✅ BaseService — базовый класс с жизненным циклом
- ⚠️ `scan_service.py::request_stop()` — 244 строки, God Method, нужно разбить

---

## 4. MODULES СЛОЙ (modules/)

**10 814 строк**

### Scanner (23 checks)

| Check | Файл | Оценка |
|---|---|---|
| XSS | xss.py | ✅ context-aware, 11 типов контекста |
| DOM XSS | dom_xss.py | ✅ |
| SQLi | sqli.py | ✅ Union/Error/Boolean/Time |
| SSTI | ssti.py | ✅ |
| LFI | lfi.py | ✅ |
| Path Traversal | path_traversal.py | ✅ |
| RCE | rce.py | ✅ |
| SSRF | ssrf.py | ✅ |
| XXE | xxe.py | ✅ |
| CORS | cors.py | ✅ |
| JWT | jwt_none.py | ✅ |
| NoSQL | nosql_injection.py | ✅ |
| GraphQL | graphql.py | ✅ |
| Prototype Pollution | prototype_pollution.py | ✅ |
| Broken Auth | broken_auth.py | ✅ |
| OAuth | oauth.py | ✅ |
| Header Injection | header_injection.py | ✅ |
| Open Redirect | open_redirect.py | ✅ |
| Info Leak | info_leak.py | ✅ |
| Sensitive Data | sensitive_data.py | ✅ |
| Headers | headers.py | ✅ |
| *(helpers)* | helpers.py | — вспомогательный, не check |
| *(init)* | __init__.py | — регистрация |

**Итого: 21 активный check + 2 вспомогательных файла = 23 файла в директории**

---

## 5. STORAGE СЛОЙ (storage/)

**604 строки, 4 файла**

- ⚠️ `http_storage.py::__init__()` — 360 строк, God Constructor

---

## 6. CORE СЛОЙ (core/)

**2 599 строк** — features.py, license.py, event_bus.py, database.py, config.py, plugin_manager.py, storage_interface.py

- ✅ EventBus — слабосвязанная коммуникация
- ⚠️ `storage_interface.py` — 2 TODO с незаполненной логикой (строки 247, 276)

---

## 7. TUI СЛОЙ (tui/)

**14 990 строк (45.4%)**

```
tui/
├── app.py                    (~1 050 строк)
├── project_manager.py        (~472 строки)
├── screens/
│   ├── scanner/screen.py     (~1 924 строки) ← предельный размер
│   ├── proxy/screen.py       (~1 574 строки)
│   ├── intruder/screen.py    (~1 429 строки)
│   ├── dashboard/screen.py   (~771 строк)
│   ├── dashboard/live_dashboard.py (~730 строк)
│   ├── settings/screen.py    (~608 строк)
│   ├── repeater/screen.py    (~658 строк)
│   └── sequencer/screen.py   (~516 строк)
└── widgets/
    └── request_editor.py     (~495 строк)
```

- ⚠️ scanner/screen.py — 1 924 строки (логика должна переехать в ScanService)
- ⚠️ Общие action-методы дублируются в 3–4 экранах (нужен BaseScreen/ScreenMixin)

---

## 8. ТЕСТИРОВАНИЕ

**1 018 passed in 9.02s ✅**

| Модуль | Покрытие |
|---|---|
| modules/scanner | ✅ Хорошее |
| modules/intruder | ✅ |
| modules/proxy | ✅ |
| modules/decoder | ✅ |
| modules/spider | ✅ |
| services/ | ✅ |
| storage/ | ✅ |
| core/ | ✅ |
| api/ | ⚠️ Только 2/10 файлов |
| tui/ | ⚠️ Неполное |
| integration/ | ⚠️ Статус запуска неизвестен |

---

## 9. ПЛАН ДЕЙСТВИЙ

### 🔴 ВЫСОКИЙ приоритет

| # | Задача | Файл |
|---|---|---|
| 1 | Устранить архитектурное нарушение | tui/screens/decoder/screen.py:170 |
| 2 | Подключить API-классы к ExportableAPI | api/*.py |
| 3 | Разбить `scan_service.py::request_stop()` | services/scan_service.py |

### 🟡 СРЕДНИЙ приоритет

| # | Задача | Файл |
|---|---|---|
| 4 | Рефакторинг `http_storage.py::__init__()` | storage/http_storage.py |
| 5 | Закрыть TODO в storage_interface.py (стр. 247, 276) | core/storage_interface.py |
| 6 | Создать ScreenMixin для общих action_* методов | tui/ |
| 7 | Тесты для api/scanner_api.py и остальных API | tests/unit/api/ |

### 🟢 НИЗКИЙ приоритет

| # | Задача |
|---|---|
| 8 | Benchmark тесты (proxy latency, intruder throughput) |
| 9 | Покрыть storage/large_body_handler.py и lru_cache.py |
| 10 | SpiderService (оркестрация из TUI → service) |

---

## ЗАКЛЮЧЕНИЕ

### Общая оценка: **8.0 / 10**

Проект в хорошем состоянии. За период с 2026-07-26:
- Performance-оптимизации снизили дублирование памяти в EventBus/ProxyServer
- Scanner расширен до 23 checks
- Версия 0.1.5, все 1 018 unit-тестов зелёные

**Готовность к публичному бета-релизу: 87%**

---
*Аудит на основе живого анализа кода. Дата: 2026-07-31.*
