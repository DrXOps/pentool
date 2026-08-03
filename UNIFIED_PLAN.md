# План развития Pentool (3-7 августа 2026)

**Цель:** Довести проект до production-ready состояния за 4 дня  
**Методология:** Только проверенные пункты, без дублирования уже реализованного

---

## ПРИОРИТЕТ 1: ЮЗАБИЛИТИ (День 1 — 3 августа)

### Proxy — базовые улучшения
- [ ] **(3ч) P-1: Комментарии к запросам**
  - Добавить колонку `comment TEXT DEFAULT ''` в таблицу `requests`
  - UI: поле ввода в инспекторе Proxy
  - **Файлы:** `pentool/storage/http_storage.py`, `pentool/tui/screens/proxy/screen.py`

- [ ] **(4ч) P-2: Тегирование и цветовые метки**
  - Добавить колонки `tags TEXT DEFAULT ''`, `color TEXT DEFAULT ''` в `requests`
  - UI: контекстное меню "Add Tag", фильтр по тегу в FilterBar
  - Цветная подсветка строк в таблице
  - **Файлы:** `pentool/storage/http_storage.py`, `pentool/tui/screens/proxy/screen.py`, `pentool/tui/widgets/filter_bar.py`

### Repeater — критичное для работы
- [ ] **(2ч) R-2: Beautify JSON/XML**
  - Кнопка "Beautify" в тулбаре RequestEditor
  - `json.dumps(indent=2)` для JSON, `xml.dom.minidom.parseString().toprettyxml()` для XML
  - **Файлы:** `pentool/tui/widgets/request_editor.py`

### Scanner — подсказки пользователю
- [ ] **(1ч) UX-9: Описание пассивного режима**
  - Добавить Static с текстом рядом с переключателем Passive
  - Текст: "Пассивный режим: анализ без отправки дополнительных запросов"
  - **Файлы:** `pentool/tui/screens/scanner/screen.py`

- [ ] **(2ч) UX-4: Tooltip для кнопок Scanner**
  - Добавить поддержку `tooltip` в `ToolbarButton` (через Textual Tooltip API)
  - Добавить tooltip для кнопок Stop, Resume, Clear
  - **Файлы:** `pentool/tui/widgets/toolbar_button.py`

**Итого День 1:** 12 часов работы

---

## ПРИОРИТЕТ 2: МЕЛКИЕ ПРАВКИ (День 2 — 4 августа)

### Критические баги
- [ ] **(2ч) БАГ-E: Гонка _project_loaded**
  - Убрать `self._project_loaded = True` из строки 1081 в `project_manager.py`
  - Переместить установку флага в конец `_new_project_sequence` и `_open_project_sequence`
  - **Файлы:** `pentool/tui/project_manager.py`
  - **Приоритет:** 🔴 Высокий

- [ ] **(1ч) БАГ-F: Перезапись .db без предупреждения**
  - В методе `new_project` добавить проверку `Path(path).exists()`
  - Показывать диалог подтверждения перезаписи
  - **Файлы:** `pentool/tui/project_manager.py`
  - **Приоритет:** 🟡 Средний

### Средние баги
- [ ] **(3ч) БАГ-C: Утечка _pending_req_ids**
  - Добавить периодическую очистку через `set_interval` (каждые 5 минут)
  - Удалять записи старше 10 минут
  - **Файлы:** `pentool/tui/screens/proxy/screen.py`
  - **Приоритет:** 🟡 Средний

- [ ] **(2ч) БАГ-D: HTTPClient не переиспользуется в Intruder**
  - Создавать один `HTTPClient` на атаку, передавать в `_send_request`
  - Закрывать после завершения атаки
  - **Файлы:** `pentool/modules/intruder.py`
  - **Приоритет:** 🟢 Низкий (оптимизация)

### UX-улучшения (если останется время)
- [ ] **(2ч) UX-3: Расхождение счетчиков req/s**
  - Унифицировать источник метрик или явно подписать каждый счётчик
  - Dashboard: "(все запросы)", Scanner: "(только сканер)"
  - **Файлы:** `pentool/tui/screens/dashboard/screen.py`, `pentool/tui/screens/scanner/screen.py`

- [ ] **(1ч) БАГ-B: Точечный аудит NoMatches**
  - Проверить все `query_one` в фоновых колбэках Intruder, Target, Repeater
  - Обернуть в `try/except NoMatches: return`
  - **Файлы:** `pentool/tui/screens/intruder/screen.py`, `pentool/tui/screens/target/screen.py`

**Итого День 2:** 11 часов работы

---

## ПРИОРИТЕТ 3: СКАНЕР — качество проверок (День 3 — 5 августа)

### Критические улучшения checks
- [ ] **(3ч) S-1: Content-Type фильтр в XSS**
  - В `XSSCheck.analyze()` добавить проверку `Content-Type` перед анализом
  - Пропускать если НЕ содержит `text/html`, `text/xml`, `application/xhtml`, `application/xml`
  - **Файлы:** `pentool/modules/scanner/checks/xss.py`
  - **Обоснование:** Предотвращает бесполезные проверки JSON/binary ответов

- [ ] **(4ч) S-2: Ограничение пейлоадов в SQLi/LFI/RCE**
  - Оставить топ-15 пейлоадов для обычного режима
  - Остальные — только при `deep_scan=True` (подготовка к будущему)
  - **Файлы:** `pentool/modules/scanner/checks/sqli.py`, `lfi.py`, `rce.py`
  - **Обоснование:** Сейчас слишком медленно (546 строк в sqli.py)

- [ ] **(3ч) S-4: OOB для XXE и Header Injection**
  - В `xxe.py` добавить OOB-пейлоады через `get_oob_helper()` по аналогии с `ssrf.py`
  - То же для `header_injection.py`
  - **Файлы:** `pentool/modules/scanner/checks/xxe.py`, `header_injection.py`
  - **Обоснование:** Blind XXE часто не детектируется без OOB

- [ ] **(2ч) S-9: CORS preflight проверка**
  - В `cors.py` добавить отправку OPTIONS-запроса
  - Анализировать `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`
  - **Файлы:** `pentool/modules/scanner/checks/cors.py`

### Общие улучшения
- [ ] **(2ч) SC-1: Глобальный таймаут на check**
  - Обернуть каждый check в `asyncio.wait_for(..., timeout=30)`
  - Логировать timeout как warning
  - **Файлы:** `pentool/modules/scanner/engine.py` или базовый класс

**Итого День 3:** 14 часов работы

---

## ПРИОРИТЕТ 4: ПОКРЫТИЕ ТЕСТАМИ до 50% (День 4 — 6-7 августа)

**Текущее состояние:** 33% общее покрытие  
**Цель:** Довести до 50% за 2 дня (реалистично)  
**Фокус:** Модули с низким покрытием, которые легко тестировать

### Низковисящие фрукты (День 4 утро — 6 августа)
- [ ] **(4ч) Покрыть pentool/utils/cert.py с 35% до 80%**
  - Тесты на генерацию сертификатов, валидацию, экспорт
  - **Файлы:** `tests/unit/utils/test_cert.py`
  - **Обоснование:** Утилита, легко тестировать изолированно

- [ ] **(4ч) Покрыть pentool/tui/widgets/toolbar_button.py с 58% до 95%**
  - Тесты на состояния (active, inactive, disabled), события Pressed
  - **Файлы:** `tests/unit/tui/widgets/test_toolbar_button.py`
  - **Обоснование:** Простой виджет, высокий ROI

### TUI виджеты (День 4 вечер — 6 августа)
- [ ] **(6ч) Покрыть pentool/tui/widgets/request_editor.py с 25% до 60%**
  - Тесты на загрузку/сохранение текста, syntax highlighting, события Changed
  - **Файлы:** `tests/unit/tui/widgets/test_request_editor.py`
  - **Обоснование:** Критичный виджет для Repeater/Intruder

- [ ] **(4ч) Покрыть pentool/tui/widgets/filter_bar.py с текущего до 70%**
  - Тесты на фильтрацию по методу, хосту, статусу, scope
  - **Файлы:** `tests/unit/tui/widgets/test_filter_bar.py`

### Storage и services (День 5 — 7 августа)
- [ ] **(6ч) Покрыть pentool/storage/http_storage.py до 70%**
  - Тесты на add_request, get_requests, update_response, FTS5 поиск
  - **Файлы:** `tests/unit/storage/test_http_storage.py`
  - **Обоснование:** Критичный модуль, нужна стабильность

- [ ] **(4ч) Покрыть pentool/services/* до 60%**
  - Тесты на ProxyService, ScannerService, RepeaterService
  - **Файлы:** `tests/unit/services/test_*_service.py`

**Итого День 4-5:** 28 часов работы (14ч/день)

---

## ОТЛОЖЕНО (не укладывается в дедлайн 7 августа)

### Новые модули
- JWT Editor (расширенный) — 2-3 дня работы
- Autorize (IDOR) — 2 дня
- Param Miner — 1-2 дня
- HTTP Request Smuggler — 3-4 дня
- Cache Poisoning Scanner — 2 дня
- Report Generator (PDF) — уже есть JSON/HTML, PDF требует 1-2 дня

### Новые Scanner checks
- idor.py — 2 дня (нужна логика повтора запросов с разными ID)
- http_smuggling.py — 3 дня (сложная логика CL.TE/TE.CL)
- file_upload.py — 1 день
- race_condition.py — 2 дня (интеграция с Turbo Intruder)
- retire_js.py — 1 день
- param_miner.py — 2 дня
- deserialization.py — 2 дня

### Дополнительные Proxy/Repeater фичи
- P-4: Редактирование WS-фреймов — 3 дня (сложная логика)
- P-5: Авто-выделение параметров в Intruder — 1 день
- R-3: Undo/Redo проверка — 0.5 дня (если сломано)
- R-4: Цветовая маркировка вкладок — 1 день
- R-5: Тайминг-диаграмма — 1 день

### Покрытие тестами выше 50%
- Довести до 70-80% — минимум 1-2 недели дополнительной работы
- TUI screens (Scanner, Proxy, Repeater) — сложно тестировать, требует моков Textual

---

## КАЛЕНДАРНЫЙ ПЛАН

### 3 августа (Суббота) — ЮЗАБИЛИТИ
- 09:00-12:00: P-1 Комментарии к запросам (3ч)
- 13:00-17:00: P-2 Тегирование и цветовые метки (4ч)
- 17:00-19:00: R-2 Beautify JSON/XML (2ч)
- 19:00-20:00: UX-9 Описание пассивного режима (1ч)
- 20:00-22:00: UX-4 Tooltip для кнопок (2ч)

### 4 августа (Воскресенье) — МЕЛКИЕ ПРАВКИ
- 09:00-11:00: БАГ-E Гонка _project_loaded (2ч)
- 11:00-12:00: БАГ-F Перезапись .db (1ч)
- 13:00-16:00: БАГ-C Утечка _pending_req_ids (3ч)
- 16:00-18:00: БАГ-D HTTPClient в Intruder (2ч)
- 18:00-20:00: UX-3 Счетчики req/s (2ч)
- 20:00-21:00: БАГ-B Аудит NoMatches (1ч)

### 5 августа (Понедельник) — СКАНЕР
- 09:00-12:00: S-1 Content-Type фильтр в XSS (3ч)
- 13:00-17:00: S-2 Ограничение пейлоадов (4ч)
- 17:00-20:00: S-4 OOB для XXE и Header Injection (3ч)
- 20:00-22:00: S-9 CORS preflight (2ч)
- 22:00-24:00: SC-1 Глобальный таймаут (2ч)

### 6 августа (Вторник) — ПОКРЫТИЕ ТЕСТАМИ (часть 1)
- 09:00-13:00: Покрыть utils/cert.py (4ч)
- 14:00-18:00: Покрыть toolbar_button.py (4ч)
- 19:00-01:00: Покрыть request_editor.py (6ч)

### 7 августа (Среда) — ПОКРЫТИЕ ТЕСТАМИ (часть 2)
- 09:00-13:00: Покрыть filter_bar.py (4ч)
- 14:00-20:00: Покрыть http_storage.py (6ч)
- 20:00-24:00: Покрыть services/* (4ч)

---

## ИТОГОВАЯ ОЦЕНКА

| Приоритет | Задач | Часов | Дни |
|-----------|-------|-------|-----|
| П1: Юзабилити | 5 | 12 | 1 |
| П2: Мелкие правки | 6 | 11 | 1 |
| П3: Сканер | 5 | 14 | 1 |
| П4: Покрытие тестами | 6 | 28 | 2 |
| **ИТОГО** | **22** | **65** | **5** |

**Реалистичность:** 65 часов / 5 дней = 13 часов/день (напряжённо, но выполнимо при фокусе)

---

## КРИТЕРИИ ГОТОВНОСТИ

### Must Have (к 7 августа обязательно)
- ✅ Комментарии и теги в Proxy (юзабилити)
- ✅ Beautify в Repeater (юзабилити)
- ✅ Все критические баги исправлены (БАГ-E, БАГ-F, БАГ-C)
- ✅ Content-Type фильтр в XSS (качество сканирования)
- ✅ Покрытие тестами минимум 45% (было 33%)

### Nice to Have (если успеем)
- Ограничение пейлоадов в SQLi/LFI/RCE
- OOB для XXE
- Покрытие тестами 50%+

### Откладываем на 8+ августа
- Новые модули (JWT Editor, Autorize, Param Miner)
- Новые Scanner checks (IDOR, HTTP Smuggling)
- WS-редактирование
- Покрытие тестами 70%+

---

## ЗАМЕТКИ ПО РЕАЛИЗАЦИИ

### Изменения БД (миграция)
```sql
-- Для P-1, P-2 (выполнить перед стартом)
ALTER TABLE requests ADD COLUMN comment TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN tags TEXT DEFAULT '';
ALTER TABLE requests ADD COLUMN color TEXT DEFAULT '';
```

### Зависимости
- Все задачи независимы, можно выполнять параллельно
- БАГ-E критичен — сделать в первую очередь в День 2

### Тестирование после каждого этапа
- После Дня 1: ручная проверка UI Proxy/Repeater
- После Дня 2: запустить `pytest tests/unit/ -v` (1018 тестов должны пройти)
- После Дня 3: запустить Scanner на тестовом сайте (dvwa/juice-shop)
- После Дня 4-5: проверить покрытие `python3 -m coverage report`

---

**Статус:** Готов к реализации  
**Следующий шаг:** Начать с P-1 (Комментарии к запросам) 3 августа 09:00
