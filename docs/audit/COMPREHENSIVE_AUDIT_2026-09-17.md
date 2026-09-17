gjcnf# Комплексный аудит pentool v0.3.3

**Дата:** 2026-09-17
**Версия:** 0.3.3 (develop @ 1cc5d74)
**Объём:** ~35k строк (пакет) + ~31k строк (тесты) | 7,360 .py-файлов
**Стадия:** Pre-production (Alpha → Beta)

---

## TL;DR — 10 главных выводов

1. **Архитектура в целом хорошая** — слоистая, EventBus типизированный/thread-safe, Proxy isolation (daemon subprocess), Screen Registry — лучшие практики соблюдены
2. **🔴 Слой `utils/http_client.py` импортирует `core.config`** — нарушение правила `utils ← core`, зафиксированное в CI техдолге
3. **🔴 Spider ProcessPoolExecutor с fork наследует fd прокси** — orphans блокируют порт 8080, «костыль» `_kill_orphaned_pentool()` чистит, но это симптом
4. **🔴 Системное дублирование `try/except/pass`** — ~40+ мест по всему коду, ошибки проглатываются
5. **🟡 Три God-файла:** `app.py` (1822), `ProxyScreen` (2076), `IntruderScreen` (2020) — декомпозиция необходима
6. **🟡 CLI-дублирование:** `run_headless_scan()` и `scan_active` на ~80% одинаковы
7. **🟡 API-слой — тонкие обёртки, не порт-адаптеры** — нет абстракции `IProxy`, `IIntruder` и т.д.
8. **🟡 Два парсера argv:** ручной `_run_target_mode()` дублирует click
9. **🟡 N+1 large_body в export_all_requests** — при 10k+ записей с large_body будет тормозить
10. **🟢 Config.to_dict() дублирует поля** — уже был баг (AI-настройки не сохранялись)

---

## Матрица рисков

| # | Проблема | Severity | Модуль | Усилие |
|---|----------|----------|--------|--------|
| 1 | Layer violation (utils → core) | **critical** | `utils/http_client.py` | S |
| 2 | Fork+ProcessPool наследует fd | **critical** | `modules/spider.py` | S |
| 3 | Системное try/except/pass | **critical** | ~40 мест в 15+ файлах | L |
| 4 | N+1 large_body в export | **high** | `storage/http_storage.py` | S |
| 5 | CLI-дублирование scan | **high** | `cli/headless.py` + `cli/scan.py` | M |
| 6 | Циклическая зависимость proxy/client→modules/proxy | **high** | `proxy/client.py` | M |
| 7 | Нет circuit breaker/retry/backoff | **high** | `utils/http_client.py`, proxy | M |
| 8 | `_pending_done_ids` без блокировки | **high** | `tui/app.py` | XS |
| 9 | API-слой без порт-адаптеров | **medium** | `api/*.py` | L |
| 10 | to_dict() дублирует поля | **medium** | `core/config.py` | XS |
| 11 | scan_service НЕ BaseService | **medium** | `services/scan_service.py` | XS |
| 12 | Нет healthcheck | **medium** | `app.py` | S |
| 13 | Нет составных SQLite индексов | **medium** | `storage/http_storage.py` | S |
| 14 | Crash reporter теряет лог при ошибке | **medium** | `core/crash_reporter.py` | XS |
| 15 | Spider без retry/backoff | **medium** | `modules/spider.py` | S |
| 16 | Мёртвый код/заглушки | **low** | `app.py`, `project_manager.py` | S |
| 17 | 6 reload_* функций дублируют паттерн | **low** | `tui/project_manager.py` | S |
| 18 | 4 send-to хендлера дублируются | **low** | `tui/app.py` | M |
| 19 | `_stop_proxy`/`_stop_proxy_async` дублирование | **low** | `tui/mixins/proxy_runtime.py` | S |
| 20 | 3 snapshot-теста флакят | **low** | Тесты (repeater) | L |
| 21 | `t.py` — мёртвый файл | **low** | `pentool/t.py` | XS |

---

## Приоритизированный план действий

### 🔴 P0 — Немедленно (безопасность, стабильность, ~2 дня)

| # | Действие | Файлы | Ожидаемый эффект |
|---|----------|-------|------------------|
| **P0.1** | Убрать импорт `core.config` из `http_client.py` — передавать конфиг параметром | `utils/http_client.py`, все вызывающие | Устранить layer violation |
| **P0.2** | Исправить fork fd leak в Spider — `spawn` или закрытие fd в child | `modules/spider.py`, `__main__.py` | Устранить EADDRINUSE на старте |
| **P0.3** | Аудит try/except/pass — заменить пустой pass на `logger.debug(...)` с контекстом | ~40 мест в 15+ файлах | Не терять ошибки |
| **P0.4** | Разорвать циклическую зависимость `proxy/client→modules/proxy` — выделить общий тип | `proxy/client.py`, `modules/proxy.py` | Чистая архитектура |
| **P0.5** | Добавить threading.Lock на `_ending_done_ids` | `tui/app.py:311` | Убрать гонку |

### �тт P1 — Следующая итерация (производительность, наблюдаемость, ~3 дня)

| # | Действие | Файлы | Ожидаемый эффект |
|---|----------|-------|------------------|
| **P1.1** | N+1 large_body fix — батчевая/асинхронная загрузка | `storage/http_storage.py` | Скорость export |
| **P1.2** | Объединить CLI scan — единый `ScanRunner` | `cli/headless.py`, `cli/scan.py` | −80% дублирования |
| **P1.3** | Заменить ручной `_run_target_mode` на click | `__main__.py` | Единый парсер |
| **P1.4** | Выделить `action_quit()` cleanup в единый `_close_all_storages()` | `tui/app.py` | −50 строк |
| **P1.5** | Добавить healthcheck — метод `health()` + CLI `pentool status --verbose` | `app.py`, `cli/` | Наблюдаемость |
| **P1.6** | Crash reporter fallback — писать локально при ошибке отправки | `core/crash_reporter.py` | Не терять краш-логи |
| **P1.7** | Retry + exponential backoff в Spider | `modules/spider.py` | Устойчивость краула |
| **P1.8** | Добавить составные SQLite индексы | `storage/http_storage.py`, `core/db_schema.py` | Скорость запросов |
| **P1.9** | to_dict() — autofix через `dataclasses.asdict()` | `core/config.py` | Не дублировать поля |

### 🟢 P2 — Техдолг (качество кода, тесты, ~2 дня)

| # | Действие | Файлы | Ожидаемый эффект |
|---|----------|-------|------------------|
| **P2.1** | Декомпозиция `app.py`: вынести CSS в .tcss, BINDINGS в константы | `tui/app.py` | −200 строк |
| **P2.2** | ScanService → BaseService (единый миксин) | `services/scan_service.py` | Консистентность |
| **P2.3** | Удалить мёртвый код: `t.py`, `_exit_caller_stack` упоминания | `pentool/t.py`, `app.py` | Чистота |
| **P2.4** | Объединить `_stop_proxy` / `_stop_proxy_async` | `tui/mixins/proxy_runtime.py` | −90% дублирования |
| **P2.5** | Универсальный `DataTableWidget` для Proxy/Intruder/Scanner | `tui/widgets/` | −400-600 строк |
| **P2.6** | Переписать 6 reload_* функций через параметризацию | `tui/project_manager.py` | −50 строк |
| **P2.7** | Переписать 4 send-to хендлера через общий `_send_to_module()` | `tui/app.py` | −60 строк |

---

## Этап 1 — Архитектура (top-down)

### 1.1 Текущая архитектура

**Слоистая (Layered)** с заявленным направлением:

```
utils ← core ← modules ← api/ ← tui/cli/plugins
```

Фактически — **трёхслойная с протеканием**:
- **Слой 0 (инфра)**: `utils/`, `core/`
- **Слой 1 (бизнес-логика)**: `modules/`, `services/`, `storage/`, `proxy/`
- **Слой 2 (интерфейсы)**: `api/`, `tui/`, `cli/`

### 1.2 Карта модулей и связей

```
                    ┌──────────────────────────────────────┐
                    │  TUI (app.py + 11 screens)           │
                    │  Mixins: ProxyRuntime, Events, ...    │
                    └──┬──────────────┬─────────────────────┘
                       │  messages    │  api/
                       ▼              ▼
                ┌──────────────┐ ┌───────────────┐
                │  services/   │ │  api/          │
                │  ProxySvc    │ │  ProxyAPI      │
                │  IntruderSvc │ │  IntruderAPI   │
                │  ScanSvc     │ │  ScannerAPI    │
                │  RepeaterSvc │ │  SpiderAPI     │
                └──────┬───────┘ └───────┬────────┘
                       │                 │
                       ▼                 ▼
                ┌──────────────┐ ┌───────────────┐
                │  modules/    │ │  storage/      │
                │  ProxyServer │ │  HttpStorage   │
                │  Intruder    │ │  BaseSqlite    │
                │  Spider      │ │  IntruderStor  │
                │  Repeater    │ └───────┬────────┘
                │  Target      │         │
                └──────┬───────┘         │
                       │                 │
                       ▼                 ▼
                ┌──────────────┐ ┌───────────────┐
                │  core/       │ │  utils/        │
                │  EventBus    │ │  http_client   │
                │  Config      │ │  parser        │
                │  features    │ │  cert          │
                │  db_schema   │ │  lightpanda    │
                └──────────────┘ └───────────────┘
```

### 1.3 Точки входа

| Точка | Файл | Описание |
|---|---|---|
| **TUI** | `__main__.main()` → `_start_tui()` → `PentoolApp().run()` | Основной вход |
| **CLI (click)** | `__main__.main()` → `cli()` (10+ команд) | Через click group |
| **Headless scan** | `__main__._run_target_mode()` → `run_headless_scan()` | CI/CD режим |
| **Proxy daemon** | `proxy/daemon.py:main()` → `ProxyDaemon.run_forever()` | Субпроцесс |
| **CLI scan** | `cli/main.py:scan` → `run_scan_command()` | Через click |

### 1.4 Нарушения слоёв (Layer violations)

| # | Файл:строка | Проблема |
|---|---|---|
| 1 | `utils/http_client.py:8` | Импортирует `from pentool.core.config` — **нарушение: utils → core** |
| 2 | `proxy/client.py:236-278` | Импортирует `core.event_bus` и `core.events` |
| 3 | `proxy/client.py:415-418` | Импортирует `modules.proxy.InterceptedRequest` — **циклическая зависимость** |
| 4 | `services/scan_service.py:22` | Импортирует `modules.scanner.helpers` — **services → modules напрямую** |
| 5 | `api/proxy_api.py:7` | Реэкспортирует `modules.proxy` — API не изолирует |
| 6 | `tui/app.py:31` | Импортирует `proxy.client` напрямую |
| 7 | `tui/app.py:46` | Импортирует `services.proxy_service` напрямую |

### 1.5 SOLID

| Принцип | Оценка | Комментарий |
|---------|--------|-------------|
| **SRP** | ⚠️ | `app.py` — 6+ ответственностей; `ProxyClient` — 3; `ScanService` — 4 |
| **DIP** | 🟡 | `BaseService` — DI есть (хорошо); `api/*` — жёсткая связь с `modules/*` (плохо) |
| **ISP** | 🟡 | `ExportableAPI` — малый интерфейс ✅; `ProxyAPI` — 20+ методов ❌ |
| **OCP/LSP** | 🟢 | Плагинная система через `plugin_manager` — ✅ |

### 1.6 God-классы

| Класс | Строк | Кандидат на декомпозицию |
|-------|-------|------------------------|
| `ProxyScreen` | **2076** | DataTable + InterceptMixin + Inspector + FilterBar + ScopeHandler |
| `IntruderScreen` | **2020** | Attack lifecycle + Results table + PayloadDropZone + FilterBar |
| `PentoolApp` | **1822** | Proxy runtime + EventBus + ProjectManager bridge + 10+ хендлеров |
| `ProxyServer` (modules) | **1037** | MITM + Scope + Intercept + Match/Replace + WebSocket |
| `AsyncSpider` | **1055** | Crawl + JS-crawl + Scheduler + Stats |
| `ProxyClient` | **566** | Subprocess mgmt + Socket protocol + Event reader |
| `ScanService` | **615** | Crawl + Scan + AI + Auto-login |

---

## Этап 2 — Узкие места (bottlenecks)

### Производительность

| # | Проблема | Файл:строка | Severity | Влияние | Рекомендация |
|---|----------|-------------|----------|---------|--------------|
| 1 | N+1 large_body в export_all_requests | `http_storage.py:369-399` | **high** | Для 10k запросов с large_body — 10k дисковых чтений | Батчевая загрузка или асинхронный I/O |
| 2 | Нет составных индексов (ORDER BY + OFFSET) | `http_storage.py:275-302` | **medium** | На 100k+ записей OFFSET = линейный скан | Составные индексы: `(id, timestamp)`, `(host, id)` |
| 3 | _find_request — линейный O(n) поиск | `modules/proxy.py:418-423` | **low** | Итерация до 1000 записей в обратном порядке | `dict[str, InterceptedRequest]` для O(1) lookup |
| 4 | _build_where — динамический SQL | `http_storage.py:516-597` | **low** | Накладные расходы на парсинг плана каждый раз | Кэш prepared statements для частых комбинаций |

### Память

| # | Проблема | Файл:строка | Severity | Рекомендация |
|---|----------|-------------|----------|--------------|
| 5 | export_all_requests загружает до 10k записей в память | `http_storage.py:350-401` | **medium** | Стриминг через generator / курсор |
| 6 | FTS5 индексирует все тела — потенциальный рост | `http_storage.py:46-48` | **medium** | Асинхронное/отложенное индексирование |
| 7 | `_pending_done_ids` может расти бесконечно | `app.py:311` | **low** | TTL-кэш или bounded set |

### Конкурентность

| # | Проблема | Файл:строка | Severity | Влияние | Рекомендация |
|---|----------|-------------|----------|---------|--------------|
| 8 | Fork+ProcessPool наследует fd прокси | `modules/spider.py:58-75` | **critical** | Orphans (PPID=1) блокируют порт 8080 | Использовать `spawn` или закрывать fd в child |
| 9 | `_pending_done_ids` set без блокировки | `app.py:311` | **high** | Потенциальная гонка из нескольких потоков | threading.Lock |
| 10 | HTTPClient.send() без таймаутов на фазы | `utils/http_client.py:68-122` | **medium** | CancelledError не чистит ресурсы | aiohttp.ClientTimeout с connect/sock_read |

### Сеть и I/O

| # | Проблема | Файл:строка | Severity | Рекомендация |
|---|----------|-------------|----------|--------------|
| 11 | Нет retry/backoff в Spider | `modules/spider.py` | **medium** | Exponential backoff (1-3 попытки) |
| **12** | Crush reporter — ssl=False без коментария | `core/crash_reporter.py:68` | **low** | Дбавить CA-сертификат или коментарий |
| **13** | new_event_loop() на кажлый crash | `core/crash_reporter.py:84-86` | **low** | Испольовать `asyncio.run()` |

### Наблюдаемость

| # | Прблема | Severity | Рекмендация |
|---|---------|----------|-------------|
| 14 | Нет healthcheck | **medium** | `health()` метд в app.py + CLI `pentool status` |
| 15 | Нет метрик EventBus (latency, throughput) | **low** | Счётчики emit/sec, handler lateny |
| 16 | Crash reporter теряет лог при ошибке | **low** | Fallback — `~/.config/pentool/crash_last.log` |

---

## Эап 3 — Пэлементный разбор

### Core

| Модуль | Сильные стороны | Слаые меса |
|---------|----------------|-------------|
| **Config** | Observer patern, overide, типизирован | `to_dict()` дублирует ai_* поля; `update()` не сораняет |
| **EventBus** | Thread-safe, Subscriion, reay | Нет backpessure; 10k событий в паяти всегда |
| **License** | ed25519, path taversal защита | 804 строки — кандидат на разбивку |
| **db_schema** | Миграции, WAL | Нет индексов на `attack_id`, `host` |

### Modules

| Модуль | Сильные стороны | Слабые места |
|--------|----------------|--------------|
| **Proxy** (1037) | Зрелый MITM, scope, intercept, WS | `_handle_http` — 190 строк; intercept_queue maxsize=2000 |
| **Spider** (1055) | ProcessPool, JS-crawl, Lightpanda | Глобальный `_PROC_POOL` thread-unsafe; нет retry |
| **Intruder** (924) | Продвинутые атаки, payloads | Смешение API и persistence |

### Services

| Модуль | Проблема |
|--------|----------|
| **ScanService** (615) | НЕ наследует BaseService (неконсистентно с IntruderService) |
| **TechDetector** (502) | Синхронный I/O внутри async-приложения |
| **ProxyService** (311) | Хорошая DI |

### Storage

| Модуль | Сильные стороны | Слабые места |
|--------|----------------|--------------|
| **BaseSqliteStorage** | Единое persistent-соединение, WAL, checkpoint | Нет connection health check |
| **HttpStorage** (597) | FTS5, LargeBodyHandler, миграции | `_build_where` — 80 строк ручного SQL; дублирование сериализации |

### TUI

| Модуль | Строк | Ключевая проблема |
|--------|-------|-------------------|
| app.py | 1822 | God-класс: compose + handlers + proxy + AI + spider |
| ProxyScreen | 2076 | God-класс: DataTable + Intercept + Inspector + FilterBar |
| IntruderScreen | 2020 | God-класс: Attack + Results + Payloads + FilterBar |
| project_manager | 632 | 6 reload_* функций — дублирование |

### CLI

| Модуль | Проблема |
|--------|----------|
| `headless.py` + `scan.py` | 80% дублирования между `run_headless_scan()` и `scan_active` |
| `__main__.py` | Два парсера argv: ручной `_run_target_mode` и click |

---

## Этап 4 — Дублирование и «разъезд» логики

### Дублирование

| # | Что дублируется | Где | Решение |
|---|----------------|-----|---------|
| 1 | try/except/pass | ~40 мест, 15+ файлов | Декоратор `@safe(log_msg=...)` |
| 2 | CLI scan | `cli/headless.py`, `cli/scan.py` | Единый `ScanRunner` |
| 3 | `_stop_proxy` / `_stop_proxy_async` | `proxy_runtime.py` | Общий `_do_stop_proxy()` |
| 4 | 4 send-to хендлера | `app.py:1349-1485` | `_send_to_module(module_id, raw)` |
| 5 | 6 reload_* функций | `project_manager.py` | Параметризованный reload |
| 6 | Сериализация header/body | `http_storage.py:136-224` | `_serialize_body()`, `_serialize_headers()` |
| 7 | LargeBodyHandler.load + decode | `http_storage.py:318-387` | `_load_body_with_fallback()` |

### Copy-paste с мутациями

| # | Блок | Различаются |
|---|------|-------------|
| 1 | on_send_to_repeater / intruder / scanner | Тип данных, сообщение пользователю (2-3 строки) |
| 2 | on_sync_scope_to_target / to_proxy | Направление синхронизации (зеркально) |

### Мёртвый код

| # | Что | Где |
|---|-----|-----|
| 1 | `t.py` | `pentool/t.py` — 1 строка `pass` |
| 2 | `_exit_caller_stack` | `app.py` — удалён, но комментарии остались |
| 3 | `on_bus_scan_progress` | `app.py:1700` — пустое тело |
| 4 | `_switch_storage_db`, `_open_project_sequence` | `project_manager.py` — заглушки совместимости |

---

## Сильные стороны (что НЕ трогать)

- **EventBus** — типизированный, thread-safe, с историей/replay — качественная реализация
- **Proxy isolation** — daemon-процесс через unix sockets — правильное решение
- **ed25519 подпись PRO-пакета** + path traversal защита — безопасно
- **License система** — grace period, trial, key binding — продумана
- **BaseSqliteStorage** — единое persistent-соединение, WAL, checkpoint на close
- **Config Observer** — реактивность без polling
- **Screen Registry** — централизованная карта модуль→экран
- **LargeBodyHandler** — вынос тел >1MB на диск
- **Faulthandler + all-thread dump** при аварийном выходе
- **Crash reporter** с анонимным пинг-счётчиком
- **~1425 тестов** — отличное покрытие для 35k строк

---

## Оценка трудоёмкости

| Приоритет | Задач | Оценка |
|-----------|-------|--------|
| **P0** 🔴 | 5 задач | **~2 дня** |
| **P1** 🟡 | 9 задач | **~3 дня** |
| **P2** 🟢 | 7 задач | **~2 дня** |
| **Итого** | **21 задача** | **~7 дней** |