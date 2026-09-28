# План: Унификация системы фильтрации таблиц — СТАТУС

## ✅ Выполнено (Этап A + B + D)

### Этап A: Базовый фреймворк — ✅
- `pentool/collections/filter_predicate.py` — FilterOp, FilterPredicate, FilterSpec, FilterField, FilterFieldType
- `pentool/tui/widgets/filter_bar_widget.py` — FilterBarWidget, Cycler
- `pentool/tui/widgets/filter_connector.py` — FilterableScreenMixin, SqlFilterAdapter
- `pentool/collections/__init__.py` — пакет

### Этап B: Адаптация баров — ✅
- `ProxyFilterBar` (`proxy_filter_bar.py`) — HTTP History: Host/LIKE, Method/IN, Status/BETWEEN, Mark/EQ, Search/FTS, Scope, Comments
- `WsFilterBar` (`proxy_filter_bar.py`) — WS History: Host/LIKE, URL/LIKE, Status/BETWEEN, Search/FTS, Scope
- `IntruderFilterBar` (`intruder_filter_bar.py`) — Status/EQ, Length/GT/LT, Grep/REGEX, Extract/REGEX, Only-matches
- `HttpStorage._build_where()` — FilterSpec → SQL
- `ProxyService._effective_filters()` — FilterSpec → scope expansion
- Удалены старые файлы: `filter_bar.py`, `filter_bar_base.py`, `intruder_results.py`, `http_history_filters.py`
- Убран `_ProxyFilterBarBase` (лишняя ступень наследования)

### Этап D: Тесты и документация — ✅
- `tests/unit/collections/test_filter_predicate.py` (68 тестов) — все 16 операторов, комбинирование, сериализация
- `tests/unit/storage/test_filter_build_where.py` (14 тестов) — FilterSpec → SQL WHERE
- `tests/unit/tui/test_intruder_filter_bar.py` (9 тестов) — collect() → FilterSpec
- `tests/unit/tui/test_http_history_filters.py` (3 теста) — FilterSpec composition
- `wiki/filter_system.md` — документация архитектуры

---

## ⏳ Осталось

### B2: IntruderStorage SQL фильтрация — ❌ НЕ ВЫПОЛНЕНО
Intruder всё ещё фильтрует in-memory (`FilterSpec.apply()`). Нужно:
- `IntruderStorage.get_results()` — принимать опциональный `FilterSpec`
- Строить WHERE из `spec.to_sql()`
- Убрать in-memory `_rebuild_table_data()` с `FilterSpec.apply()`

### C2: FileSelector фильтр — ❌ НЕ ВЫПОЛНЕНО
FileSelector диалог использует vanilla `DataTable`, нет фильтра по имени/расширению.
Выполнить, если будет востребовано.

### IntruderFilterBar — узкий терминал
13 виджетов в `height: 1` — при ширине терминала <140 символов кнопки обрезаются.
Фикс: либо уменьшить количество полей, либо разбить на 2 строки.

---

## Итог
- **Выполнено:** ~90% плана
- **Не выполнено:** IntruderStorage SQL, FileSelector фильтр
- **Удалено:** LoadFromProxy диалог (мёртвый код)
- **Тестов:** 94 шт, все зелёные