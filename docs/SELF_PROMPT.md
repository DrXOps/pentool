# SELF-PROMPT: Правила сессий — не повторять этих ошибок

> Этот файл читается в начале каждой сессии. Здесь — зафиксированные грабли.
> **Текущий тест-счёт: 842u + 9s (все зелёные)** *(851 total с snapshot-тестами)*

---

## 🚫 ОШИБКИ ДОКУМЕНТАЦИИ

### 1. LazyHttpTable — НЕ СУЩЕСТВУЕТ
- ❌ Нельзя: писать `LazyHttpTable` где угодно
- ✅ Надо: `textual_fastdatatable.DataTable` + `ArrowBackend(pa.Table.from_pylist(...))`

### 2. Единственная точка записи HTTP-истории — `HttpStorage`
- ❌ Нельзя: `INSERT INTO` для HTTP-запросов вне HttpStorage; обращаться к таблице `request_logs` или `http_history`
- ✅ Надо: `HttpStorage.add_request()` → таблица `requests` → TUI читает через ArrowBackend
- ✅ Dashboard `_fetch_stats` запрашивает таблицу `requests` (НЕ `http_history`)

### 3. Статусы этапов — следить за актуальностью
- При завершении этапа: обновить PLAN.md И создать/обновить `docs/modules/[module].md`

---

## 🚫 АРХИТЕКТУРНЫЕ ОШИБКИ

### 4. TUI не импортирует modules/ напрямую
```
utils ← core ← modules ← api/ ← tui / cli / plugins
```
- ❌ `from pentool.modules.proxy import ProxyServer` в TUI-экране
- ✅ `from pentool.api.proxy_api import ProxyAPI` → `app.get_proxy_api()`

### 5. `is_running` — property без скобок
```python
if proxy.is_running:      # ✅
if proxy.is_running():    # ❌
```

### 6. Thread-safe доступ к asyncio из TUI
- ❌ `proxy.intercept_enabled = True` из TUI-треда
- ✅ `proxy.set_intercept(True)` → `loop.call_soon_threadsafe(...)`

### 7. `push_screen` vs `push_screen_wait`
- `push_screen_wait()` требует worker → зависает если вызван не из worker
- ✅ `push_screen(dialog, callback)` — синхронный callback-стиль

### 8. ScanEngine не имеет `_findings`
- ❌ `engine._findings = []` — атрибута нет, данные хранятся в SQLite
- ✅ `engine.save_findings(findings)` через фоновый поток с `threading.Event`

### 9. EventBus — нет двойного emit
- ❌ `_on_active_finding` не должен повторно emit-ить `FindingDiscovered` — это вызывает рекурсию
- ✅ ScanService emit-ит событие сам; subscriber только добавляет в таблицу

---

## 🚫 TEXTUAL / FASTDATATABLE — ЛОВУШКИ

### 10. После замены backend — сбрасывать ВСЕ кэши
```python
table.backend = ArrowBackend(pa.Table.from_pylist(rows))
table._ordered_columns = None   # ← ОБЯЗАТЕЛЬНО
table._clear_caches()
table._require_update_dimensions = True
table.refresh()
```

### 11. `HeaderSelected.column_index` — int, не ColumnKey
```python
col_name = self._col_names[event.column_index]   # ✅
col_name = event.column_key.value                 # ❌
```

### 12. Завершение приложения
```python
self.exit()
asyncio.get_event_loop().call_later(0.1, os._exit, 0)  # ✅ даём Textual 100мс
os._exit(0)  # ❌ терминал останется в raw mode
```

### 13. jemalloc в pyarrow
```python
pa.jemalloc_set_decay_ms(0)  # В on_mount для корректного завершения
```

### 14. Контекстное меню — правый клик не работает в VTE
- VTE перехватывает button=3 (правый клик), до Textual не доходит
- ✅ Используем: Ctrl+клик (button=1+ctrl) или клавиша `m`

### 15. `detail-panel` height и overflow
- `overflow: hidden hidden` при `height: 0` → дочерние TextArea получают нулевые размеры
- ✅ Убрать overflow с `#detail-panel`; после `styles.height = 18` вызвать `panel.refresh(layout=True)`

---

## 🚫 ОШИБКИ ПЛАНИРОВАНИЯ

### 16. НИКАКИХ ТИХИХ УПРОЩЕНИЙ В ПЛАНАХ
- ❌ Откидывать проблемы из исходного документа без явной пометки
- ✅ Все проблемы включать в план. Если откладываем — явно указать почему и когда

### 17. Фейковый функционал — запрещён
- При открытии проекта из Recent Projects РЕАЛЬНО загружать данные (исправлено в DCX)
- `export_project_data()` должен читать из SQLite, а не только из RAM
- Boot animation — не показывать "OK" для модулей которые реально не проверяются

---

## 📋 РАБОЧИЙ ПРОЦЕСС

### При старте сессии
1. Прочитать MEMORY.md → определить текущий этап
2. Прочитать PLAN.md → знать актуальный статус
3. Прочитать `docs/modules/[relevant].md` → знать детали модуля

### Переход к новому этапу
- ТОЛЬКО после явного подтверждения пользователя
- Обновить PLAN.md (статус в таблице + текущие задачи)
- Создать/обновить `docs/modules/[module].md`

### Создание новых модулей
1. Сначала `pentool/modules/[name].py` — бизнес-логика без TUI
2. Затем TUI-экран с реальными виджетами (не заглушка)
3. Затем тесты в `tests/unit/modules/test_[name].py`
4. Обновить PLAN.md статус
