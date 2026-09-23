# Комплексный аудит pentool — статус BETA (2026-09-23)

**Дата оригинала:** 2026-09-17  
**Обновлено:** 2026-09-23  
**Стадия:** Beta  

---

## ✅ Что починено (удалено из аудита)

- Краш сортировки Proxy History — `safe_sort()`, crash-guard
- Тормоза `_find_request` — O(1) кэш `_request_cache`
- Краулер мигает — `spider_crawl_finished` в `finally`
- Scanner payload — убран `[dim]` из Type
- AI-счётчик — работает
- Shift+B — есть нотификация
- `_pending_done_ids` — Lock добавлен
- CLI-дублирование scan — `ScanRunner` на `ScanService`
- `scan_service.py` — наследует `BaseService`
- `to_dict()` — AI-поля сохранены
- Config Observer — работает
- Headless AIWorker — через ScanService с fingerprint
- MCP сервер — n_ctx fallback, _ensure_alive, _extract_json array-first
- Target AI чекбокс — скрыт при ai_enabled=False
- error_guard.py — внедрён в app.py и intruder/screen.py

---

## 🔴 Актуальные проблемы (не исправлены)

### P0 — Критические
| # | Проблема | Severity | Модуль |
|---|----------|----------|--------|
| 1 | Layer violation — `utils/http_client.py` импортирует `core.config` | **critical** | `utils/http_client.py` |
| 2 | Fork+ProcessPool наследует fd прокси — `_kill_orphaned_pentool()` костыль | **critical** | `modules/spider.py` |
| 3 | Системное `try/except/pass` — ~30+ мест ещё не заменены на `err()` | **critical** | ~15 файлов |

### P1 — Архитектурные
| # | Проблема | Severity | Модуль |
|---|----------|----------|--------|
| 4 | N+1 large_body в export_all_requests | **high** | `storage/http_storage.py` |
| 5 | Циклическая зависимость `proxy/client→modules/proxy` | **high** | `proxy/client.py` |
| 6 | Нет circuit breaker/retry/backoff в http_client | **high** | `utils/http_client.py` |
| 7 | API-слой без порт-адаптеров (нет IProxy, IIntruder) | **medium** | `api/*.py` |
| 8 | Нет healthcheck | **medium** | `app.py` |
| 9 | Нет составных SQLite индексов | **medium** | `storage/http_storage.py` |
| 10 | Crash reporter теряет лог при ошибке | **medium** | `core/crash_reporter.py` |
| 11 | Spider без retry/backoff | **medium** | `modules/spider.py` |
| 12 | Мёртвый код/заглушки | **low** | `app.py`, `project_manager.py` |
| 13 | 6 reload_* функций дублируют паттерн | **low** | `tui/project_manager.py` |
| 14 | `_stop_proxy`/`_stop_proxy_async` дублирование | **low** | `tui/mixins/proxy_runtime.py` |
| 15 | 3 snapshot-теста флакят | **low** | Тесты (repeater) |
| 16 | `t.py` — мёртвый файл | **low** | `pentool/t.py` |
| 17 | God-файлы: app.py (1822), ProxyScreen (2076), IntruderScreen (2020) | **medium** | декомпозиция |

### P2 — AIWorker пробелы
| # | Проблема | Модуль |
|---|----------|--------|
| 18 | `_verify_queue` не подключён — TP/FP верификация | `pro/.../ai_worker.py` |
| 19 | Engine не забирает из `ai_payload_queue` | `pro/.../scan_orchestrator.py` |
| 20 | audit_log не показывает items — порядок нормализации | `services/ai/provider.py` |
| 21 | AIWorker не останавливается при `request_stop()` | `pro/.../ai_worker.py` |
| 22 | `prioritize_params` не вызывается | `pro/.../ai_worker.py` |

### P3 — UI/UX
| # | Проблема | Модуль |
|---|----------|--------|
| 23 | Колонка Payload в Scanner findings — вынести в отдельную колонку | `pro/.../scanner/screen.py` |
| 24 | Асинхронная загрузка large_body | `tui/screens/proxy/screen.py` |

---

## Техдолг
Полный список: `/home/docx/pentool/MYPLANS/tech_debt.md`