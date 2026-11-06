# TUI — соглашения (после аудита 2026-11-06)

Правила, которые действуют для любого нового кода в `pentool/tui/`. Каждое
правило выведено из конкретной находки — ссылки ведут в
[`REPORT.md`](REPORT.md), обоснования — в [`DECISIONS.md`](DECISIONS.md).

Коротко: **если хендлер не вызывается — виноват не Textual, а имя.**
Доминирующий класс дефектов в этом слое — «код написан, но не диспетчеризуется».

---

## 1. Обработчики сообщений

### 1.1 `@on(...)` в миксине запрещён

Textual собирает `@on`-хендлеры в `__init_subclass__` **конкретного класса**
(`textual/message_pump.py` — обход `class_dict`, не MRO). Миксин без
`MessagePump` в базе не получает `_decorated_handlers` вовсе, и хендлер
молча не вызывается. Именованные хендлеры **резолвятся по MRO** — поэтому
в миксине допустимы только они.

```python
# ✗ никогда не сработает, если класс — обычный миксин
class ClipboardMixin:
    @on(ContentPanel.CopyRequested)
    def _on_copy(self, event): ...

# ✓ резолвится по MRO
class ClipboardMixin:
    def on_content_panel_copy_requested(self, event: ContentPanel.CopyRequested) -> None: ...
```

Проверяется: `tests/unit/tui/test_handler_name_dispatch.py` (F-001, ADR-3).

### 1.2 Имя хендлера выводится из `__qualname__` сообщения

`Message.handler_name` = `"on_"` + snake_case(`__qualname__`). Вложенные
классы дают полное имя с именем владельца:

| Сообщение | `handler_name` |
|---|---|
| `StartStopWidget.StartRequested` | `on_start_stop_widget_start_requested` |
| `ContentPanel.PasteRequested` | `on_content_panel_paste_requested` |
| `Input.Blurred` | `on_input_blurred` |
| `ProxyDataTable.ScrolledToTop` | `on_proxy_data_table_scrolled_to_top` |

Двойное подчёркивание (`on_proxy_data_table_scrolled_to_top` не
`on__proxy_…`) нужно **только** для классов с ведущим подчёркиванием
(`_BaseHttpWidget` → `on__base_http_widget_…`). Ошибка на одно подчёркивание
и есть F-041 — три мёртвых хендлера в `ProxyScreen`.

Проверяется тем же тестом.

### 1.3 Не выдумывать сообщения

Перед тем как писать `on_<widget>_<event>`, проверить, что тип существует:

```python
from textual.widgets import DataTable
DataTable.RowActivated          # AttributeError в Textual 8 (F-044)
from textual.widgets import Static
Static.Clicked                  # нет такого — Static не постит клик (F-043)
```

Мышь на `Static` ловится `on_click(event: events.Click)`. Двойной клик —
`event.chain == 2` (проверено на `pilot.click(..., times=2)`).

### 1.4 Виджет → родителю через `Message`, не через DOM

```python
# ✗ ищет «первого предка с таким методом», попадает в чужой экран
node = self.parent
while node:
    if hasattr(node, "_open_context_menu"):
        node._open_context_menu(...)
    node = node.parent

# ✓ сообщение доставляется ровно владельцу по DOM-пути
self.post_message(self.ContextMenuRequest(event.screen_x, event.screen_y))
```

ADR-10.

---

## 2. Воркеры

### 2.1 Только существующий API

`WorkerManager` (`textual/worker_manager.py`) имеет ровно шесть операций:
`add_worker`, `cancel_all`, `cancel_group`, `cancel_node`, `start_all`,
`wait_for_complete`. **Нет** `cancel(name)`, `get_worker(name)`,
`remove_worker(name)` — вызов любого из них даёт `AttributeError`, который
`except Exception` превращает в тихий no-op (F-045).

### 2.2 Группа на каждую задачу

```python
self.run_worker(
    self._do_auto_save(task, name),
    name=name,                          # только для логов
    group=self.SAVE_WORKER_GROUP,       # по этой строке идёт отмена
    exclusive=False,
    exit_on_error=False,
)
...
self.workers.cancel_group(self, self.SAVE_WORKER_GROUP)
```

Имя воркера — для логов и отладки. Адресация отмены — группа. Причина:
нельзя отменить «все автосейвы» по шести разным именам, не зная их наперёд.

### 2.3 Не подменять жизненный цикл Textual

`asyncio.create_task(...)` вне `run_worker` не отменяется при закрытии
экрана и продолжает писать в закрытую БД (F-014, 2 места остаются).
Если задача переживает экран — это `run_worker` с `group`, а не голая
задача.

### 2.4 Не блокировать event loop

Работа с БД, сеть, файлы — в воркере. В теле хендлера — только постановка
воркера (ADR-1, п.3).

---

## 3. Подписки на глобальные источники

### 3.1 Пара «подписка ↔ отписка» обязательна

| Источник | Где подписка | Где отписка |
|---|---|---|
| `EventBus` (уровень виджета) | `on_mount` / `_init_…` | `on_unmount` |
| `Config.add_observer` (уровень App) | `PentoolApp.on_mount` | `_on_exit_app` |
| `EventBus` (уровень App) | `on_mount` | `_on_exit_app` |

Хендлер хранится в атрибуте — иначе `unsubscribe` не сможет его передать
(лямбда при каждом вызове — новый объект). Готовый образец:
`mixins/ai_sync.py::AiModeSyncMixin`.

### 3.2 `_on_exit_app` — единственный выход

`action_quit` не покрывает `app.exit()` из кода, закрытие по сигналу и
падение. `_on_exit_app` вызывается на любом пути выхода (ADR-12).

---

## 4. Слои

Порядок: `utils ← core ← modules ← api ← services ← tui`. Проверяется
`tools/check_layers.py` (pre-commit, CI).

- `tui → modules` и `tui → storage` запрещены. Если функции нет в `api/` —
  фасад добавляется в `services/` (прецедент: `services/tech_detector.py`).
- Composition root один — `PentoolApp` (ADR-1, ADR-4).
- БД — только через `*API` / `*Service`, только в воркере.
- Путь к БД берётся из публичного `app.db_path`; `app._db_path`,
  `getattr(self.app, "_db_path", …)`, `self.app.__dict__` — нет (F-004, F-016).

---

## 5. Исключения

| Контекст | Допустимо |
|---|---|
| Виджет mounted без App (`notify`, `query_one` на опциональном) | `except NoMatches` / `except Exception` с `logger.exception` |
| Хендлер, действие, воркер | `except Exception` **только** с `logger.exception(...)` |
| Вспомогательный метод из хендлера | пусть всплывает — диспетчер покажет |

`except Exception: pass` в новом коде запрещён. Существующие 278 мест
чинятся при касании файла, а не массовым PR — ADR-6. Причина в том, что
именно они скрывали F-001…F-005 и F-041…F-045.

---

## 6. ID, классы, CSS

### 6.1 id — kebab-case и без значений по умолчанию у контейнеров

`Toolbar`, `ContentPanel` и другие контейнеры **не** задают `id` по
умолчанию: все экраны смонтированы одновременно внутри `ContentSwitcher`,
и общий `id="toolbar"` делает `query_one("#toolbar")` недетерминированным
(F-006, F-018). Textual генерирует уникальный id сам.

Префиксы: `btn-*` (кнопки), `panel-*` / `cp-*` (панели), `tab-*`, `screen-*`.

### 6.2 Цвета — только токены

Разрешены `$text`, `$text-muted`, `$text-disabled`, `$panel`, `$surface`,
`$surface-lighten-1/-2`, `$surface-darken-1`, `$primary`,
`$primary-darken-1/-2/-3`, `$success`, `$warning`, `$error`, `$accent`,
`$background` и производные через `%`. Hex и `rgb()` — нет. Сейчас их 0 —
поддерживаем.

### 6.3 CSS — в `.tcss`

Новый виджет получает `DEFAULT_CSS = (Path(__file__).parent / "x.tcss").read_text(...)`,
а не строку в `.py`. Строкой — только для 10 существующих классов (F-025),
перевод — при следующем касании файла.

---

## 7. Тесты

- Каждый экран и каждый виджет с сообщениями — минимум один тест,
  проверяющий **эффект**, а не отсутствие исключения (F-034 — образец
  того, как четыре теста без `assert` пропустили P0).
- Отмена воркеров тестируется на настоящем `WorkerManager`
  (`TestCancelReachesWorkerManager`), а не на фейке с придуманным API.
- Фейк воспроизводит **поверхность** настоящего объекта: у фейкового
  менеджера воркеров — те же шесть методов, иначе тест повторяет ошибку
  кода.
- UI-тесты — `app.run_test()` + `pilot`; `await pilot.pause()` после
  каждого действия, влияющего на воркер или на монтирование.

---

## 8. Чеклист перед коммитом

```bash
uvx pre-commit run --files $(git diff --name-only HEAD)   # или --all-files
uv run python tools/check_layers.py
uv run ruff check --select F pentool/tui
scripts/run-tests.sh                                      # гейт tests/unit
```

Плюс вручную, если правка про хендлеры:

- имя совпадает с `Message.handler_name` (спросить у самого класса:
  `MyMessage.handler_name`);
- `@on` не попал в миксин;
- новое сообщение где-то постится;
- новая подписка снимается там же, где заводится.
