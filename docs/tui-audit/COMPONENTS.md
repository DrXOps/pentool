# TUI — каталог компонентов

Что уже есть в `pentool/tui/` и когда это брать вместо нового класса.
Отсортировано по назначению. «Сообщения» — то, на что подписывается
владелец; имена обработчиков вычисляются из них (§1.2
[`CONVENTIONS.md`](CONVENTIONS.md)).

Все пути — относительно `pentool/tui/`.

---

## 1. Каркас экрана

| Компонент | Файл | Назначение | Когда брать |
|---|---|---|---|
| Экраны | `screens/*/screen.py` | Экраны — `Widget`, монтируются один раз в `compose()` App | Новый модуль = новый `Widget`-экран + запись в `screen_registry.SCREEN_MAP` |
| `BaseModuleScreen` | `screens/base.py` | Общий каркас модульного экрана: табы, базовая навигация | Любой экран с вкладками |
| `TabbedContentPanel` | `widgets/tab_panel.py` | Изолированные табы: свой `TabPane`, свои виджеты, своя БД-строка | Экран с «документами» (запросы, атаки, сравнения) |
| `AiModeSyncMixin` | `mixins/ai_sync.py` | Синхронизация UI с `Config.ai_enabled`; подписка снимается в `on_unmount` | Экран показывает/скрывает AI-элементы |
| `AppMixin` | `mixins/app_mixin.py` | Доступ к публичному API приложения (`app.db_path`, `notify`) | Вместо `self.app._something` |
| `NotificationsMixin` | `mixins/notifications.py` | Единый `notify`/`err` с префиксами модуля | Любое уведомление |
| `ContentClipboardMixin` | `mixins/content_clipboard_mixin.py` | Copy/Paste для всех `ContentPanel` экрана | Экран содержит `ContentPanel` с кнопками ⧉/⎘ |
| `AutoSaveMixin` | `mixins/autosave.py` | Отслеживаемые отменяемые воркеры автосохранения | Экран пишет state в БД в фоне |
| `RequestContextMenuMixin` | `mixins/request_context_menu.py` | Общее контекстное меню запроса | Экран показывает HTTP-запросы |
| `ProxyRuntimeMixin` | `mixins/proxy_runtime.py` | Старт/стоп прокси из App | Только `PentoolApp` |
| `ProxyEventHandlersMixin` | `mixins/events_handlers.py` | Мост EventBus → сообщения TUI | Только `PentoolApp` |
| `ProjectAutoSaveMixin` | `mixins/project_autosave.py` | Сохранение проекта по таймеру | Только `PentoolApp` |
| `DialogCancelMixin` | `mixins/dialog_cancel.py` | `action_cancel() → dismiss(None)` | В базе диалога (уже в `BaseDialog`) |

---

## 2. Контейнеры и панели

| Компонент | Файл | Сообщения | Заметки |
|---|---|---|---|
| `Toolbar` | `widgets/toolbar.py` | — | `ToolbarButton`, `Toolbar.sep()`, `.progress()`, `.counter()`. `id=None` по умолчанию — **не задавать общий id** (F-006) |
| `ToolbarButton` | `widgets/toolbar_button.py` | `Pressed` | `handler: on_toolbar_button_pressed`; варианты — классы `variant-success` / `variant-warning` / `active` / `warn` / `disabled` |
| `StartStopWidget` | `widgets/start_stop_widget.py` | `StartRequested`, `PauseRequested`, `ResumeRequested`, `StopRequested` | Единственный механизм Start/Pause/Resume/Stop (`StartStopMixin` удалён, F-019) |
| `ContentPanel` | `widgets/content_panel.py` | `CopyRequested`, `PasteRequested`, `FormatToggleRequested` | `RichLog` или `TextArea` + кнопки в заголовке; `content_widget`, `get_text()`, `set_title()`, `clear_content()` |
| `RequestEditor` / `ResponseViewer` / `HttpView` | `widgets/request_editor.py` | — | Подклассы `ContentPanel`: подсветка HTTP/JSON/XML, форматирование |
| `ResizeHandle` | `widgets/resize_handle.py` | — | Горизонтальный/вертикальный разделитель; `vertical=True` для вертикальной ориентации |
| `DiffPanel` | `widgets/diff_panel.py` | — | Показ unified diff |
| `InspectorPanel` | `widgets/inspector_panel.py` | — | Боковая панель деталей запроса |
| `PayloadDropZone` | `widgets/payload_drop_zone.py` | `PayloadsLoaded` | Drop-зона для файлов payload'ов |
| `ContextMenu` | `widgets/context_menu.py` | `ItemSelected` | Всплывающее меню (обычно `app.show_context_menu(...)` проще) |

---

## 3. Таблицы

| Компонент | Файл | Сообщения | Заметки |
|---|---|---|---|
| `ArrowBackendDataTable` | `widgets/data_table.py` | — | База: данные из pyarrow-таблицы |
| `SortableTableMixin` | `widgets/data_table_mixins.py` | — | Сортировка по клику на заголовок |
| `ProxyDataTable` | `widgets/proxy_data_table.py` | `ScrolledToTop`, `CommentIconClicked`, `ContextMenuRequest` | Специализация для истории прокси; постит сообщения, а не ищет методы у предков (ADR-10) |
| `IntruderResultsTable` | `widgets/intruder_results_table.py` | — | Результаты атаки + колонка извлечения |

Правило: таблица **никогда** не обращается к экрану напрямую. Новое
взаимодействие = новое вложенное `Message`.

---

## 4. Фильтры, поиск, ввод

| Компонент | Файл | Сообщения | Заметки |
|---|---|---|---|
| `FilterBarWidget` | `widgets/filter_bar_widget.py` | `FilterChanged` | База: `configure()` → список `FilterField`, `predicates()` → `FilterSpec` |
| `ProxyFilterBar`, `WsFilterBar` | `widgets/proxy_filter_bar.py` | `FilterChanged` | Наследники под прокси и WebSocket |
| `IntruderFilterBar` | `widgets/intruder_filter_bar.py` | `FilterChanged` | Результаты атаки |
| `Cycler`, `ToggleButton` | `widgets/filter_bar_widget.py` | `Changed`, `Toggled` | Внутренние для фильтр-баров; в новом коде — `OptionCycler` |
| `OptionCycler` | `widgets/option_cycler.py` | `Changed` | Циклер для одиночного значения (поглощает `Cycler`, F-020 — отложено) |
| `SearchBar` | `widgets/search_bar.py` | `Search`, `TargetToggle`, `Closed` | Поиск в панели; переключатели — `on_click`, у `Static` нет click-сообщения (F-043) |
| `NiceCheckbox` | `widgets/nice_checkbox.py` | — | Чекбокс с глифом `[✓]` вместо `▐X▌` |

---

## 5. Индикация и хром

| Компонент | Файл | Заметки |
|---|---|---|
| `StatusBar` | `widgets/statusbar.py` | Нижняя строка статуса |
| `GlobalHintBar`, `ModuleHintBar` | `widgets/keyhintbar.py` | Подсказки клавиш; цвета клавиш — `_GLOBAL_KEY_COLORS` |
| `HintBarBase` | `widgets/hintbar_base.py` | `set_text(markup)` |
| `ActivityIndicator` | `widgets/activity_indicator.py` | Индикатор активности модулей (`_Tracked`-чекеры) |
| `ModuleTabs` | `widgets/module_tabs.py` | Переключение модулей; постит `ModuleSelected` в App |
| `CustomNotify` | `widgets/custom_notify.py` | Замена стандартного тоста |

---

## 6. Диалоги

| Компонент | Файл | Базовый класс |
|---|---|---|
| `BaseDialog` | `dialogs/base_dialog.py` | `DialogCancelMixin + ModalScreen`; даёт `DEFAULT_CSS`, `Binding("escape", "cancel")` |
| `ConfirmDialog` | `dialogs/confirm.py` | ✅ `BaseDialog` |
| `GenerateDialog`, `InputDialog`, `SmartPayloadsDialog`, `TextInputDialog`, `RecrawlDialog` | `dialogs/*.py` | ✅ `BaseDialog` |
| `CertInstallDialog`, `ColorPickScreen`, `CommentDialog`, `FileSelectorDialog`, `IntruderAutoMarkDialog`, `LightpandaViewer`, `LoadFromProxyDialog`, `MatchReplaceDialog`, `SaveProjectDialog`, `LoadProjectDialog`, `ScopeDialog` | `dialogs/*.py` | ⬜ прямой `ModalScreen` — миграция отложена (F-024) |

**Новый диалог пишется только от `BaseDialog`**, даже если сосед по
каталогу этого не делает. `Binding("escape", "dismiss(None)")` работает
(проверено, F-037 опровергнута), но с `BaseDialog` это не нужно писать
вообще.

---

## 7. Матрица «задача → компонент»

| Задача | Берём |
|---|---|
| Новая кнопка в тулбаре | `ToolbarButton` внутри `Toolbar` (без общего `id`) |
| Старт/стоп долгой операции | `StartStopWidget` + четыре `*Requested`-хендлера |
| Текст + копирование/форматирование | `ContentPanel` (или `RequestEditor`/`ResponseViewer`) |
| Копирование в экране | `ContentClipboardMixin` в списке баз класса |
| Фильтр по набору полей | `FilterBarWidget` + наследник с `configure()` |
| Список однотипных документов | `TabbedContentPanel` |
| Фоновая запись в БД | `AutoSaveMixin._start_save_worker` |
| AI-зависимые элементы | `AiModeSyncMixin` + `_sync_ai_ui()` |
| Модальное окно | `BaseDialog` |
| Показ ошибки/успеха | `NotificationsMixin` / `app.notify` |
| Обратная связь виджет→экран | вложенный `Message` + именованный хендлер |

---

## 8. Чего в каталоге нет — и почему

- **DI-контейнер / порты `Protocol`** — ADR-4: на текущем числе
  потребителей абстракция дороже выгоды. Сервисы приходят через
  конструктор, где это возможно (F-012 — долг).
- **Готовый `protocol`-адаптер БД** — три экрана получают путь к БД
  четырьмя способами (F-016); единый способ — задача после F-012.
- **Виртуализованный список** — таблицы на `DataTable`, а не на
  `ListView`; для 10⁵ строк это уже проверено (pyarrow-бэкенд).
