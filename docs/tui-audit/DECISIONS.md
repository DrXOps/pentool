# TUI Audit — DECISIONS (ADR)

**Дата:** 2026-11-06 · **Textual:** 8.2.8 · **Ветка:** `audit/tui-refactor-2026-11-06`

Формат: **Контекст → Решение → Последствия**. Ссылки на находки — `REPORT.md` (`F-NNN`).

---

## ADR-1. Целевая архитектура TUI-слоя

**Контекст.** TUI — 21 269 строк и самый связный слой. Правило слоёв
`utils ← core ← modules ← api ← tui` уже соблюдается (`tools/check_layers.py` → 0 нарушений). Но App сам создаёт инфраструктуру (F-012), а экраны достигают БД четырьмя способами (F-016).

**Решение.** Сохранить существующее направление зависимостей и зафиксировать три правила:

```
┌─────────────────────────────────────────────┐
│  tui/  (Widget, screens, widgets, dialogs)   │
│     ├── messages.py  — намерения вверх       │
│     └── mixins/      — поведение, не данные  │
├─────────────────────────────────────────────┤
│  api/      (facade-объекты: ProxyAPI, …)     │
├─────────────────────────────────────────────┤
│  services/ (ProxyService, tech_detector)     │
├─────────────────────────────────────────────┤
│  modules/ + storage/ + core/                 │
└─────────────────────────────────────────────┘
Composition root: PentoolApp.__init__ / on_mount — единственное место,
где tui импортирует api/services/core.
```

1. **`tui → modules` запрещён** — если функции нет в `api/`, фасад добавляется в `services/` (прецедент: `tech_detector.py` — обёртка над PRO `modules/scanner/*`).
2. **`tui → storage` запрещён** — всё через `ProxyService` / `*API`.
3. **Работа с БД — только в воркерах** (`run_worker` / `@work`), никогда в теле хендлера.

**Последствия.** Портов в виде `Protocol` не вводим (ADR-4); правило проверяется расширением `tools/check_layers.py` на `tui → services/storage` (не входит в этот аудит).

---

## ADR-2. Сообщения: единая иерархия и направление

**Контекст.** `messages.py` — плоский список 15 классов, поле `req: object` (4 места), нет базового класса, нет префикса namespace.

**Решение.**

| Направление | Механизм | Пример |
|---|---|---|
| Виджет → владелец | вложенный `Message` с `control`-property | `ToolbarButton.Pressed`, `ContentPanel.CopyRequested` |
| Экран → экран | через **App**, `tui/messages.py` | `SendToRepeater`, `SyncScopeToProxy` |
| Домен → TUI | EventBus + мост-миксин | `ProxyRequestCaptured` → `ProxyEventHandlersMixin` → `ProxyRequestAdded` |

Соглашения:
- имена — глагол-в-прошедшем для факта (`Captured`, `Completed`), императив-запрос для намерения (`SendToRepeater`, `SyncScopeToTarget`);
- `req: object` → `InterceptedRequest` через `TYPE_CHECKING`-импорт (не ломает слой: `pentool.api.proxy_api` уже импортируется в `app.py`);
- мёртвые классы удаляются, а не «оставляются на будущее» (F-039, `ProxyClearHistory`).

**Последствия.** `messages.py` остаётся плоским — на 15 классах иерархия дороже, чем экономит. Правило: новый класс обязан иметь хотя бы одного producer и одного handler в одном PR.

---

## ADR-3. `@on(...)` внутри миксинов запрещён

**Контекст.** F-001: `@on` в обычном классе-миксине не регистрируется. Textual собирает `_decorated_handlers` в `__init_subclass__` **конкретного класса** по `class_dict` (`textual/message_pump.py:79-93`), а не по MRO.

**[проверено]** оба варианта:

| Способ | Миксин работает? |
|---|---|
| `@on(Message)` в обычном классе | **нет** (`/tmp/mixin_on_test2.py`: 0 vs 1) |
| `def on_content_panel_copy_requested(self, e)` в обычном классе | **да** (`/tmp/handler_name_test.py`: hits 1, обход MRO в `message_pump.py:797-801`) |

**Решение.**
1. В миксинах, чей хост — `Widget`/`App`, обработчики объявляются **соглашением об именах** (`on_<handler_name>`), а не `@on`.
2. Запрещено добавлять `@on` в `mixins/`; проверка — `tools/check_tui_css.py`-аналог или grep в code-review.
3. Если нужен selector-матчинг (`@on(X, "#id")`) — миксин обязан наследовать `Widget` (тогда он реально участвует в MRO-MessagePump).

**Последствия.** Миксины становятся «поведением без декораторов». `events_handlers.py:5-12` содержит комментарий, утверждающий обратное («Textual не видит `@on` в миксинах» — верно, но делает вывод «поэтому держим в app.py» вместо «поэтому не используем `@on`»); комментарий переписан.

---

## ADR-4. Composition root без DI-контейнера

**Контекст.** Синглтоны `get_config()` / `get_event_bus()` / `HotkeyRegistry` живут в `core`. Полный переход на Protocol-порты — рефактор на сотни строк и 292 теста.

**Решение.** Синглтоны **остаются**, но:
1. Composition root — только `PentoolApp` (уже так);
2. экран получает зависимости **через конструктор** там, где это возможно (`ProxyScreen(proxy_service=…)` уже есть — передавать его, а не присваивать `_proxy_service` извне, F-012);
3. в тестах подмена — `monkeypatch.setattr("pentool.core.config.get_config", …)` (уже практикуется).

**Последствия.** `Protocol`-порты — отдельная итерация, только когда появится второй потребитель. Сейчас DI-контейнер добавит абстракцию без выгоды.

---

## ADR-5. Дизайн-система: базовые компоненты

**Контекст.** F-017 (4 копии paste), F-019 (два Start/Stop), F-020 (два Cycler), F-021 (три фильтр-бара), F-024 (11 диалогов мимо базы), F-038 (CSS-дубли 25 %).

**Решение — каталог (реализовано в этом аудите помечено ✅):**

| Паттерн | Компонент | Файл | Статус |
|---|---|---|---|
| Кнопка тулбара | `ToolbarButton` | `widgets/toolbar_button.py` | есть ✅ |
| Тулбар | `Toolbar` + `Toolbar.sep/progress/counter` | `widgets/toolbar.py` | есть, `id=None` по умолчанию ✅ |
| Start/Pause/Resume/Stop | `StartStopWidget` | `widgets/start_stop_widget.py` | единственный ✅ (`StartStopMixin` удалён) |
| Панель с заголовком + кнопки | `ContentPanel` | `widgets/content_panel.py` | есть ✅ |
| Копирование/вставка содержимого | `ContentClipboardMixin` (именованные хендлеры) | `mixins/content_clipboard_mixin.py` | исправлен ✅ |
| Диалог | `BaseDialog` (+ `DialogCancelMixin`) | `dialogs/base_dialog.py` | миграция 11 диалогов — D-итерация 4 |
| Циклер | `OptionCycler` | `widgets/option_cycler.py` | единственный (поглотит `Cycler`) |
| Фильтр-бар | `FilterBarWidget` + наследники | `widgets/filter_bar_widget.py` | есть, CSS-дубли — D-итерация 5 |
| Разделитель панелей | `ResizeHandle` | `widgets/resize_handle.py` | есть ✅ |
| AI-синхронизация экрана | `AiModeSyncMixin` | `mixins/ai_sync.py` | новый ✅ |

**Правило CSS-токенов.** Только `$text, $text-muted, $text-disabled, $panel, $surface, $surface-lighten-1/-2, $surface-darken-1, $primary, $primary-darken-1/-2/-3, $success, $warning, $error, $accent, $background` + производные `%`. Hex/rgb запрещены (сейчас — 0, поддерживаем).

**Нейминг:** id — kebab-case (`btn-*`, `tab-*`, `panel-*`, `cp-*`); классы-роли — `role-*`; классы-состояния — `-state` (Textual-конвенция: `-on`, `-active`, `-disabled`, `-dragging`); CSS-переменные — не вводим сверх текстовых токенов.

---

## ADR-6. Политика обработки исключений в TUI

**Контекст.** F-009: 615 `except Exception`, 286 → `pass`. Именно они маскируют F-001…F-005.

**Решение.**
1. В `on_*`/`action_*`/`watch_*`/воркерах: `except Exception` допустим **только** вместе с `logger.exception(...)` (не `debug`).
2. Вспомогательные методы, вызываемые из хендлеров, не глотают исключения — пусть всплывают в диспетчер.
3. `pass` без лога запрещён в новых правках; существующие — чинятся при касании файла (не массовым PR).
4. `NoMatches` из `query_one` на опциональных виджетах — явный `except NoMatches` (не `Exception`).

**Последствия.** Не включаем `ruff BLE001` (blocking) сразу: 615 мест — это неделя работы и риск регрессий. Включим после итерации 3.

---

## ADR-7. Активная адаптивность вместо пересчёта состояния

**Контекст.** F-027: единственный `on_resize` меняет **пользовательское состояние** (`_inspector_visible`), а не layout.

**Решение.** `on_resize` ставит **классы на корень экрана** по брейкпоинтам; раскладку делает CSS.

```python
# в экране
def on_resize(self, event: events.Resize) -> None:
    self.set_class(event.size.width < 80, "narrow")
    self.set_class(event.size.width >= 160, "wide")
```
```tcss
ProxyScreen.narrow #inspector-panel { display: none; }
```

Брейкпоинты: `< 80` (narrow), `80–159` (normal), `>= 160` (wide). Константы — `constants.py` (после чистки, F-007).

**Последствия.** Состояние пользователя (`_inspector_visible`) снова управляет только пользователь.

---

## ADR-8. Документация аудита — в `docs/tui-audit/`

**Контекст.** `docs/audit/` в `.gitignore` (локальная копия для агента), `docs/tui-audit/` — нет.

**Решение.** `docs/tui-audit/` версионируется: это конвенции и каталог компонентов, нужные контрибьюторам. `SUMMARY.md` — итог этого аудита, `CONVENTIONS.md` — правила, которые действуют после, `COMPONENTS.md` — каталог.

**Последствия.** Требует правки `wiki/tui.md` (см. [`wiki/CONTEXT.md`](../../wiki/CONTEXT.md) → «изменение кода требует изменения страницы»).

---

## ADR-9. `constants.py`: оставить только то, что реально импортируется

**Контекст.** F-007: 53 из 61 константы не используются нигде вне самого файла. Файл заявлен как «single source of truth for string identifiers», но id в коде живут литералами по месту.

**Решение.** Удалить неиспользуемые константы. Оставить 8 экранных (`SCREEN_*`), которые импортируются 6+ модулями: это единственные значения, на которые действительно опирается больше одного файла. Подключать остальные 53 «обратно» — механический рефактор на ~200 правок без выигрыша: id всё равно проверяются только в рантайме, а тест-гвард (см. `test_handler_name_dispatch.py`) строит карту по AST.

**Последствия.** Новые id пишутся литералом на месте. Конвенция: константа попадает в `constants.py` **только** когда её читают ≥2 модуля и она фигурирует в селекторе `query_one`/`@on`. Проверка: `grep -rn <NAME> pentool/ | wc -l`.

---

## ADR-10. Сообщения как контракт вместо обхода DOM

**Контекст.** F-041: `ProxyDataTable.on_event` искал приватный `_open_context_menu` у предков (`while node: if hasattr(node, "_open_context_menu")`), обходя собственное сообщение `ContextMenuRequest`, которое никто не постил.

**Решение.** Виджет сообщает родителю о намерении **сообщением**; хендлер `on_<owner>_<event>` реализует родитель. Никаких `hasattr`-обходов дерева и обращений к приватным методам чужих классов.

**Почему это важно помимо чистоты.** `hasattr(node, "_open_context_menu")` находит **любой** предок с таким атрибутом, включая экран, который сейчас в другом табе `ContentSwitcher`. Сообщение доставляется по DOM-пути и адресовано ровно владельцу таблицы.

**Последствия.** Новые взаимодействия виджет↔экран описываются вложенным `Message` на виджете; имена хендлеров проверяются тестом `test_handler_name_dispatch.py` (он же ловит двойное подчёркивание).

---

## ADR-11. Воркеры: группа на каждую задачу, отмена — только `cancel_group`/`cancel_node`

**Контекст.** F-045: `self.workers.cancel(...)`, `get_worker(...)`, `self.remove_worker(...)` — ни одного из этих методов нет в `textual.worker_manager.WorkerManager`. `except Exception: pass` скрывал `AttributeError`, отмена автосейва не происходила.

**Решение.**
1. Все воркеры виджета получают `group=` по назначению (`autosave` — через `AutoSaveMixin.SAVE_WORKER_GROUP`).
2. Отмена — `cancel_group(self, group)` (своя группа) или `cancel_node(screen)` (всё экрана). Имя воркера — только для логов, не для адресации.
3. Долгоживущие операции (`@work`) без `group` — долг: их нельзя отменить точечно, только `cancel_all`.

**Последствия.** `_running_save_tasks` остаётся, но как список **для логов/дебага** и как маркер «есть что отменять»; решает отмену `cancel_group`. Тест `TestCancelReachesWorkerManager` работает на настоящем `WorkerManager` и падает, если отмена перестанет доходить.

---

## ADR-12. `_on_exit_app` — единственная точка снятия глобальных подписок

**Контекст.** F-046 и F-002: и `Config.add_observer`, и `EventBus.subscribe` живут дольше приложения. `action_quit` — не единственный выход (`app.exit()` из кода, закрытие по сигналу, падение).

**Решение.** Глобальные подписки снимаются в `_on_exit_app` (вызывается после `run()` на любом пути выхода), а не в `action_quit`. Подписки уровня виджета — в `on_unmount`. Оба места обязаны быть симметричны `subscribe`/`add_observer`: правило «каждый `subscribe` в `on_mount` имеет `unsubscribe` в `on_unmount`» (или в миксине, как `AiModeSyncMixin`).

**Последствия.** Новые подписки добавляются только парами. Проверка при ревью: `grep -n "subscribe\|add_observer" <file>` и столько же `unsubscribe`/`remove_observer`.
