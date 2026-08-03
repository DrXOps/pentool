# План развития Pentool

**Последнее обновление:** 2026-08-03  
**Версия:** 0.1.8

---

## ✅ ВЫПОЛНЕНО 3 августа 2026

### Юзабилити (Приоритет 1) — ВЫПОЛНЕНО
- ✅ **P-1: Комментарии к запросам** — колонка `comment` в БД + Input в Proxy inspector, автосохранение по Enter
- ✅ **P-2: Теги и цветовые метки** — колонки `tags`/`color` в БД, диалоги Add Tag + Set Color (ModalScreen), цветные эмодзи-точки 🔴🟢🔵 в колонке Host, фильтр по тегу в FilterBar
- ✅ **R-2: Beautify JSON/XML** — кнопка `✨ Beautify` в тулбаре Repeater, `json.dumps(indent=2)` + `minidom`
- ✅ **UX-9: Описание пассивного режима** — Static с пояснением рядом с кнопкой Passive в Scanner
- ✅ **UX-4: Tooltip для кнопок** — параметр `tooltip` в ToolbarButton, добавлен для Start/Stop/Clear Scanner
- ✅ **UX-3: Расхождение счётчиков** — выполнено (tooltip на кнопках уточняет контекст)

### Баги (Приоритет 2) — ВЫПОЛНЕНО
- ✅ **БАГ-E: Гонка _project_loaded** — флаг переставлен в конец `_do_switch` после `_reload_project_screens`
- ✅ **БАГ-C: Утечка _pending_req_ids** — `set_interval(300)` + `_cleanup_pending_req_ids()` (10 мин TTL)
- ✅ **БАГ-D: HTTPClient в Intruder** — один клиент на атаку, закрывается в `finally`
- ✅ **БАГ-F (Intruder crash)**: UnboundLocalError `attack` в `_run_attack` — исправлен

### Архитектура и CI
- ✅ **Layer violations** — исправлены: `utils/http_client` не импортирует `core.config`, `tui/intruder` не импортирует `modules.intruder_turbo` напрямую
- ✅ **Scanner → PRO**: `scanner_api.py`, `tui/screens/scanner/`, `modules/scanner/` перенесены в `pentool-pro`. `required_feature = "scanner_pro"` по умолчанию для всех checks
- ✅ **PRO bootstrap**: `_bootstrap_pro()` в `pentool/__init__.py` + `pkgutil.extend_path` — автоматическая доставка из `~/.pentool/pro/` или `pro/` submodule
- ✅ **Scanner tab lock**: вкладка блокируется (disabled + tooltip) без лицензии с `scanner_pro`
- ✅ **CI зелёный**: Tests ✅ CI ✅, 1150 unit tests
- ✅ **v0.1.8 на PyPI**

### Тесты (Приоритет 4) — частично
- ✅ `utils/cert.py`: 35% → 90% (37 тестов)
- ✅ `widgets/toolbar_button.py`: 58% → 95% (18 тестов)
- ✅ `storage/http_storage.py`: 59% → 68% (26 тестов)
- ✅ `services/base_service.py`: 71% → 95% (14 тестов)
- ✅ `core/event_bus.py` Subscription: +5 тестов
- ✅ `tui/test_proxy_pending_cleanup.py`: +7 тестов (БАГ-C)
- ✅ `modules/test_intruder_http_client_reuse.py`: +4 теста (БАГ-D)
- ⬜ `tui/widgets/request_editor.py` — только `_beautify_text` покрыта, основной виджет нет
- ⬜ `tui/widgets/filter_bar.py` — не покрыта

**Итого добавлено тестов: ~111. Покрытие: 33% → ~35%**

---

## ПРИОРИТЕТ 1: СЛЕДУЮЩЕЕ (4–7 августа)

### Баги — остались
- [ ] **(1ч) БАГ-F: Перезапись .db без предупреждения**
  - В `new_project` проверять `Path(path).exists()`, показывать диалог подтверждения
  - **Файл:** `pentool/tui/project_manager.py`
  - **Приоритет:** 🟡 Средний

- [ ] **(1ч) БАГ-B: Аудит NoMatches**
  - Проверить все `query_one` в фоновых колбэках Intruder, Target, Repeater
  - Обернуть в `try/except NoMatches: return`
  - **Приоритет:** 🟢 Низкий

- [ ] **(1ч) UX-5: Resume со старым числом потоков**
  - При Resume читать актуальное значение из поля ввода, не кешированное
  - **Файл:** `pro/pentool/tui/screens/scanner/screen.py`

- [ ] **(1ч) UX-7: Подсветка синтаксиса в Intruder исчезает после Clear**
  - Сбрасывать только маркеры payload, не переинициализируя редактор

### Покрытие тестами — остались
- [ ] **(4ч) request_editor.py** — основной виджет (25% → 60%)
- [ ] **(4ч) filter_bar.py** — до 70%
- [ ] **(4ч) services/scan_service.py, proxy_service.py** — до 60%

---

## ПРИОРИТЕТ 2: СКАНЕР — качество (5 августа)

- [ ] **(3ч) S-1: Content-Type фильтр в XSS** — пропускать JSON/binary ответы
  - **Файл:** `pro/pentool/modules/scanner/checks/xss.py`

- [ ] **(4ч) S-2: Ограничение пейлоадов в SQLi/LFI/RCE** — топ-15 в обычном режиме
  - **Файлы:** `pro/pentool/modules/scanner/checks/sqli.py`, `lfi.py`, `rce.py`

- [ ] **(3ч) S-4: OOB для XXE и Header Injection**
  - **Файлы:** `pro/pentool/modules/scanner/checks/xxe.py`, `header_injection.py`

- [ ] **(2ч) S-9: CORS preflight** — OPTIONS-запрос + анализ Allow-Methods/Headers
  - **Файл:** `pro/pentool/modules/scanner/checks/cors.py`

- [ ] **(2ч) SC-1: Глобальный таймаут** — `asyncio.wait_for(..., timeout=30)` на check
  - **Файл:** `pro/pentool/modules/scanner/engine.py`

---

## ПРИОРИТЕТ 3: ОТЛОЖЕНО (8+ августа)

### Новые модули
- JWT Editor (расширенный) — 2-3 дня
- Autorize (IDOR) — 2 дня
- Param Miner — 1-2 дня
- HTTP Request Smuggler — 3-4 дня
- Report Generator (PDF) — 1-2 дня

### Новые Scanner checks
- `idor.py`, `http_smuggling.py`, `file_upload.py`, `race_condition.py`, `retire_js.py`, `param_miner.py`, `deserialization.py`

### Proxy/Repeater
- P-4: Редактирование WS-фреймов
- P-5: Авто-выделение параметров в Intruder
- R-4: Цветовая маркировка вкладок Repeater
- R-5: Тайминг-диаграмма

### Покрытие тестами 70%+
- TUI screens требуют моков Textual — 1-2 недели

---

## СОСТОЯНИЕ ПОКРЫТИЯ (2026-08-03)

| Модуль | До | После |
|--------|-----|-------|
| `utils/cert.py` | 35% | 90% ✅ |
| `widgets/toolbar_button.py` | 58% | 95% ✅ |
| `storage/http_storage.py` | 59% | 68% ✅ |
| `services/base_service.py` | 71% | 95% ✅ |
| `widgets/request_editor.py` | 25% | ~30% (только _beautify_text) |
| `widgets/filter_bar.py` | 27% | 27% (не трогали) |
| **Общее** | **33%** | **~35%** |
