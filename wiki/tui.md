# tui

**Textual-интерфейс: приложение, экраны, виджеты, диалоги, миксины и система вкладок.**

- **Связи:** [[api]], [[core]], [[deps/textual]], [[deps/textual-fastdatatable]]
- **Код:** pentool/tui/
- **Источник:** pentool/tui/; аудит TUI 2026-11-06…12 —
  `docs/tui-audit/REPORT.md` (46 находок), `DECISIONS.md`, `CONVENTIONS.md`,
  `COMPONENTS.md`
- **Обновлено:** 2026-11-12

## Назначение

Самый крупный слой (96 `.py` + 53 `.tcss`). Реализует TUI на Textual: набор
экранов модулей, общие виджеты и систему вкладок. Правило слоёв:
`tui → modules` и `tui → storage` запрещены — только через [[api]] и
[[services]].

## Публичный интерфейс

- `PentoolApp` (`app.py`) — корневое приложение; монтирует экраны, содержит
  `ContentSwitcher` и условную загрузку PRO-экранов (Scanner, Recon).
- `screen_registry.py` — `SCREEN_MAP`, реестр экранов, ленивые импорты.
- `BaseModuleScreen` (`screens/base.py`) — база для экранов с вкладками.
- **Система вкладок**: `widgets/tab_panel.py::TabbedContentPanel` (Generic по
  типу состояния), `_TabState` / `_IntruderTabState`, стабильный `tab_uid`.
- Экраны: `proxy`, `repeater`, `intruder`, `decoder`, `comparer`, `sequencer`,
  `target`, `dashboard`, `extensions`, `settings`.
- `constants.py` — только 8 `SCREEN_*`, которые импортирует второй модуль
  (F-007); id одного экрана живёт литералом рядом со своим виджетом.

---

## Правила: как писать TUI-код

Единственный доминирующий класс дефектов в этом слое — **«код написан, но
никогда не выполняется»**: хендлер с неверным именем, CSS-селектор мимо DOM,
сообщение, которое никто не постит, константа, которую никто не импортирует.
Ошибки нет — просто ничего не происходит. Поэтому почти каждое правило ниже
закрыто исполняемым гвардом, а не дисциплиной.

### 1. Сначала найти, потом писать

Перед новым классом — пройти по каталогу компонентов
(`docs/tui-audit/COMPONENTS.md`, раздел 7 «задача → компонент»). Готовое:

| Задача | Берём | Файл |
|---|---|---|
| Кнопка в тулбаре | `ToolbarButton` внутри `Toolbar` | `widgets/toolbar.py` |
| Start/Pause/Resume/Stop | `StartStopWidget` | `widgets/start_stop_widget.py` |
| Текст + копирование/формат | `ContentPanel` (или `RequestEditor`/`ResponseViewer`) | `widgets/content_panel.py` |
| Панель с id и кнопками | `ContentPanel` | там же |
| Переключатель значения кликом | `OptionCycler` | `widgets/option_cycler.py` |
| Фильтр по набору полей | `FilterBarWidget` / `HistoryFilterBar` | `widgets/filter_bar_widget.py` |
| Однотипные документы во вкладках | `TabbedContentPanel` | `widgets/tab_panel.py` |
| Таблица | `ArrowBackendDataTable` + `SortableTableMixin` | `widgets/data_table.py` |
| Модальное окно | `BaseDialog` | `dialogs/base_dialog.py` |
| Разделитель с ресайзом | `ResizeHandle` | `widgets/resize_handle.py` |
| Копирование панелей | `ContentClipboardMixin` | `mixins/content_clipboard_mixin.py` |
| Фоновая запись в БД | `AutoSaveMixin` | `mixins/autosave.py` |
| AI-зависимые элементы | `AiModeSyncMixin` | `mixins/ai_sync.py` |
| Ошибка/успех | `NotificationsMixin` / `app.notify` | `mixins/notifications.py` |

Два одинаковых класса вместо одного — это уже случалось: `Cycler` и
`OptionCycler` (F-020), три фильтр-бара (F-021), 11 диалогов мимо
`BaseDialog` (F-024). Гварды: `test_filter_bar_unified.py`,
`test_dialogs_unified.py`.

### 2. Стили — только `.tcss`

```python
# ✓
_CSS = (Path(__file__).parent / "my_widget.tcss").read_text(encoding="utf-8")

class MyWidget(Widget):
    DEFAULT_CSS = _CSS
```

Строка CSS в `.py` запрещена (F-025): её не видит ни гейт селекторов, ни
grep, ни подсветка. Все 10 исторических inline-CSS переведены 2026-11-12.

Дальше:

- **Цвета — только `$token`.** Hex, `rgb()`, `hsl()`, `ansi_*` запрещены:
  тема не перекрасит виджет. `!important` запрещён — он прячет конфликт
  специфичности. Сейчас ровно 0 и того, и другого (F-030).
- **`BaseDialog` уже центрирует подклассы** (`align: center middle` в его
  `DEFAULT_CSS` матчит подклассы по типу — проверено запуском `pilot`).
  Повторять `MyDialog { align: center middle }` не нужно: это шум, который
  прячет настоящую геометрию (F-024/F-038).
- **Общий селектор — один владелец.** `.toolbar-sep` объявлен в
  `widgets/toolbar_button.tcss`; повторять его в диалоге нельзя.
  Исключения — только через явный список в гварде.
- **Селектор обязан совпадать с DOM.** Гейт: `uv run python tools/check_tui_css.py`
  (CI + pre-commit). Он сверяет каждый класс/id/тип из `.tcss` с литералами в
  `pentool/tui`, включая Textual-овские типы и классы из `DEFAULT_CSS`.
- **Атрибутных селекторов в Textual 8 нет.** `[id^="…"]` — `TokenError` при
  разборе, а не «селектор мимо». Per-tab виджеты несут и id
  (`f"{suffix}-{tab_id}"`), и **класс** с той же базой; `.tcss` селектит по
  классу (F-008).
- **Не собирать `DEFAULT_CSS` из другого через `.replace()`** по имени класса:
  переименование молча ломает вторую полусотню правил (F-021). Общий стиль —
  один файл, селекторы по общему базовому классу.
- **Каждый `.tcss` должен кем-то загружаться.** Файл, который никто не
  читает, — хуже отсутствующего: он выглядит как стиль (F-038;
  `menu.tcss`, `menu_bar.tcss` — единственные два исключения, оба мёртвые).
- **Правило, корень которого — предок виджета, живёт в `app.tcss`.**
  Textual префиксует первый селектор `DEFAULT_CSS` типом самого виджета
  (`textual/css/parse.py:174`: `if scope and selectors[0].name != scope`).
  Поэтому `Screen.narrow InspectorPanel { … }`, написанное в
  `screens/proxy/screen.tcss`, разбирается как
  `ProxyScreen Screen.narrow InspectorPanel { … }` — и не совпадает никогда,
  без единой ошибки в логе. Такие правила (адаптив по ширине, глобальные
  состояния) кладём в `pentool/tui/app.tcss`, где скопа нет. Гейт этого не
  ловит: селектор валиден, он просто не матчится.

Гвард: `tests/unit/tui/test_css_hygiene.py` (четыре правила выше, проверено
мутациями: строка CSS в `.py`, hex-цвет, повторное центрирование, второй
владелец общего селектора — каждая роняет тест).

### 3. id и адресация

- **kebab-case**, префиксы: `btn-*` (кнопки), `panel-*`/`cp-*` (панели),
  `tab-*`, `screen-*`.
- **Контейнеры не задают id по умолчанию.** Все экраны смонтированы
  одновременно внутри `ContentSwitcher`; общий `id="toolbar"` делает
  `query_one("#toolbar")` недетерминированным (F-006, F-018).
- **Per-tab id строятся из константы, а не из литерала с двух сторон.**
  `_TabId` в `screens/intruder/screen.py`: 38 суффиксов, монтаж и
  `query_one` читают одну таблицу. Опечатка в литерале не ловилась ничем —
  таб монтируется, а `query_one` падает `NoMatches` только когда пользователь
  откроет именно эту вкладку (F-023/F-030). Гвард —
  `tests/unit/tui/test_intruder_tab_ids.py`.
- **Виджет ищется по `content_widget`, а не по выдуманному id.** `TextArea`
  внутри `ContentPanel` называется `#cp-body-widget`; поиск `#editor-area`
  молча падал в `except Exception` — маркер «*» не появлялся никогда
  (F-031, 2026-11-12).
- **Константы `constants.py`** — только те, что читает второй модуль; иначе они
  декорация (`test_constants_are_used.py`).
- **Состоянию, пришедшему извне, присваивается новый `tab_id`.**
  `TabbedContentPanel.action_new_tab(state=...)` берёт состояние из БД, где
  `tab_id` пустой или от прошлого запуска, и обязан переписать его на только что
  сгенерированный: per-tab id строит владелец (`_wid(tab_id, …)`), и со старым
  `tab_id` тело монтируется под одним id, а все `query_one` ищут другой —
  вкладка навсегда остаётся пустым placeholder'ом, без единой ошибки в логе.
  `tab_uid` (ключ персистентности) при этом не трогается (2026-11-12).
- **Ключи, которые читает восстановление, сверяются с теми, что пишет
  хранилище.** `dict.get("name", …)` на словаре с ключом `tab_name` не падает —
  срабатывает дефолт, и все восстановленные вкладки получают одинаковое имя.
  Гвард `test_intruder_tab_restore.py::test_every_key_read_here_is_produced_there`
  сравнивает AST-сбор `td.get(...)` в `_do_load_tabs_from_db` с ключами
  return-словаря `IntruderStorage.get_tabs`. Общее правило: у `.get()` на
  внешних данных всегда есть тихий дефолт, поэтому имя ключа — контракт,
  и его надо проверять, а не помнить.

### 4. Сообщения и хендлеры

- **`@on(...)` в обычном миксине не регистрируется** — Textual собирает
  декораторы только из `__dict__` конкретного класса. В миксинах — только
  именованные хендлеры, они резолвятся по MRO (F-001, ADR-3).
- **Имя хендлера выводится из `Message.handler_name`** = `on_` + snake_case
  от `__qualname__`. `ProxyDataTable.ScrolledToTop` →
  `on_proxy_data_table_scrolled_to_top` (одно подчёркивание); двойное — только
  у классов с ведущим `_`. Ошибка в имени = молча мёртвый хендлер (F-041).
  Гвард — `tests/unit/tui/test_handler_name_dispatch.py`.
- **Не выдумывать сообщения**: `DataTable.RowActivated` в Textual 8 нет,
  `Static.Clicked` нет (мышь на `Static` — `on_click(event: events.Click)`,
  двойной клик — `event.chain == 2`).
- **Виджет → родителю через `Message`, не через обход `self.parent`.** Обход
  «первого предка с таким методом» попадает в чужой экран (ADR-10).
- Вложенный `Message` в виджете — это норма, а не исключение: таблица ничего
  не знает об экране, она постит `ContextMenuRequest`.
- **Хендлер без виджета — мёртвый код, и он молчит.** `@on(Msg, "#some-id")`
  срабатывает только при существующем виджете с этим id; если кнопку убрали,
  а обработчик оставили, ни импорт, ни запуск, ни тесты этого не заметят.
  Так прожили пять недель «Clear results» и «Export CSV» (потеряны в
  `cb11bfd`) и кнопка Save на вкладке Settings→AI (потеряна в `0f563b3`:
  MCP-порт и путь к модели читались из конфига, но сохранить их было нечем).
  Гвард — `tests/unit/tui/test_on_selectors_resolve.py`: AST-сбор всех
  `@on(..., "#id")` против всех созданных id (`id=`, второй позиционный
  аргумент `ToolbarButton`, префикс f-строки вроде `cp-btn-{key}`).

### 5. Воркеры и асинхронность

- `run_worker(..., group=..., exit_on_error=False)` — и отмена по **группе**.
  `WorkerManager` умеет ровно шесть операций: `add_worker`, `cancel_all`,
  `cancel_group`, `cancel_node`, `start_all`, `wait_for_complete`. Вызов
  несуществующего `cancel(name)` даёт `AttributeError`, который
  `except Exception` превращает в тихий no-op (F-045).
- **Голый `asyncio.create_task` для задач внутри App запрещён** — задача не
  отменяется при закрытии экрана и пишет в закрытую БД (F-014). Прецедент:
  техдетект живёт в `auto_scope._spawn_tech_detect`, группа `tech-detect`.
- В теле хендлера — только постановка воркера; БД, сеть и файлы — внутри.
- **`mount()` асинхронен: сначала `await`, потом читать DOM.** `mount`
  планируется в очереди сообщений, а не вставляет детей сразу, поэтому
  `pane.mount(inner)`, за которым без `await` идёт `query_one`, попадает в
  «виджета ещё нет» — а `except Exception` вокруг превращает это в тихий
  no-op. Пока хелпер монтирования и загрузки данных планировались **двумя
  `call_after_refresh` в одном батче**, восстановленный из БД таб Intruder
  показывал пустой список payload'ов: `_refresh_payload_list` искал `ListView`
  раньше времени и глотал `NoMatches`. Правило: монтирование делает `async`-
  метод с `await pane.mount(...)`, и данные грузятся его последней строкой —
  один путь, один порядок. Вторая половина правила:
  `TabbedContentPanel` постит `TabCreated` **до** того, как тело таба
  собрано, поэтому пачечное восстановление из БД (вкладки создаются подряд,
  активна последняя) наполняет данными только активную; данные остальных
  приходят на `TabActivated`. Гвард —
  `tests/unit/tui/test_intruder_toolbar_wiring.py::TestRestoredTabShowsItsData`
  (пачка из двух вкладок: последняя покрашена сразу, первая — при открытии).
- **Значения per-tab виджетов берутся из состояния, а не из литерала.**
  Подпись и описание типа атаки собирались строкой «Sniper ▼», и таб,
  поднятый из БД с `battering_ram`, врал о собственном режиме. Тот же тест.
- **«Было» читается до того, как состояние обнулили.** В
  `on_intruder_filter_bar_changed` строка `had_extract = bool(...)` стояла
  после трёх присваиваний, которые очищают `tab.grep_extract_patterns`, —
  то есть всегда вычислялась уже по пустому списку. Паттерн добавлял колонку
  «Extract», а снятие фильтра её не убирало: колонка оставалась в таблице
  пустой. Гвард `test_intruder_extract_column.py` проверяет оба направления,
  а не только добавление. Общее правило: при сравнении с предыдущим
  состоянием `previous = ...` идёт первой строкой обработчика.

### 6. Подписки и таймеры

- `EventBus.subscribe` / `Config.add_observer` — всегда парная отписка:
  на уровне виджета в `on_unmount`, для App в `_on_exit_app`. Хендлер
  хранится в атрибуте, иначе `unsubscribe` нечего передать.
- `_on_exit_app` — единственный выход: `action_quit` не покрывает
  `app.exit()` из кода, сигнал и падение (ADR-12).
- **Таймеры снимать вручную не нужно**: `set_interval`/`set_timer` живут в
  `MessagePump._timers` (`WeakSet`), Textual останавливает их при unmount
  (`message_pump.py:533`, `Timer._stop_all`). Это проверено чтением исходника
  8.2.8, а не предположением (F-013). Хранить `self._ticker` незачем, если
  значение нигде не читается.

### 6a. Горячие клавиши

- **Имя клавиши — это то, что присылает парсер Textual, а не то, как клавиша
  называется на клавиатуре.** `Binding("ctrl-at", …)` принимается молча,
  печатается в футере и никогда не срабатывает. Ctrl+Space приходит как
  `ctrl+@` (классический терминал, байт NUL →
  `_ansi_sequences`: `"\x00": (Keys.ControlAt,)`) либо как `ctrl+space`
  (Kitty-протокол, `CSI 32;5u`); `ctrl-at` не производит ни один протокол.
  Поэтому «Ctrl+Space = Send» в Repeater годами работал только в pilot-тестах:
  `pilot.press("ctrl+at")` передаёт имя клавиши дословно (F-052).
- Ctrl+I и Ctrl+H недостижимы по той же причине: терминал шлёт байты Tab и
  Backspace, а `KEY_ALIASES` диспетчеризация не раскрывает. `F5` — потому что
  Textual отдаёт строчное `f5`.
- Гвард — `tests/unit/tui/test_hotkey_keys_are_reachable.py`: множество
  достижимых имён собирается из `XTermParser` и `ANSI_SEQUENCES_KEYS`, а не
  выписывается руками; список известных мёртвых клавиш — трещотка, которая
  может только сокращаться.
- **Одно действие на нескольких клавишах — норма**, копия «та же клавиша + то
  же действие» — нет: второй `Binding` не сработает никогда. Проверяет
  `test_app_startup.py::test_bindings` (`_KNOWN_UNREACHABLE` — единственное
  исключение из правила «мёртвых клавиш нет»).
- **Таблица хоткеев одна.** `defaults.py` — источник `BINDINGS` и содержимого
  реестра; экран настроек читает реестр (`registry.groups()` +
  `registry.get_entries`), а не держит свою копию: вторая копия успела
  разойтись с настоящей (там были `ctrl+i` и `ctrl+space` — клавиши из
  `_KNOWN_UNREACHABLE`). Группа хранится **ключом реестра**, а не полем
  `HotkeyEntry`: поле-копия у неглобальных записей молча оставалось
  `"global"`. Если когда-нибудь появится переназначение, оно обязано идти через
  реестр и переписывать `BINDINGS` смонтированных экранов; экран, который
  просто показывает «saved», — это дефект, а не заглушка (F-035). Гвард —
  `test_hotkey_settings_is_honest.py` (состав таблицы сверяется с реестром;
  в `compose` нет `Button`/`Input`; нет вызовов `.notify(...)`), а
  `test_hotkey_keys_are_reachable.py` берёт список групп из реестра — новая
  группа не может проскочить мимо проверки клавиш.

### 7. Диалоги

Только `BaseDialog` (`ModalScreen[_ResultT]` + `Generic[_ResultT]`, даёт
геометрию, `action_cancel()` и Escape). Свой CSS — поверх базы, без
повторного центрирования. `Binding("escape", ...)` обязан указывать на
существующий `action_*` — гвард `tests/unit/tui/test_dialogs_unified.py`
проверяет это исполнением плюс AST-сканом.

### 8. Исключения

`except Exception: pass` в новом коде запрещён (ADR-6; исторические 276 мест
чинятся при касании, рост блокирует `tools/check_silent_except.py`). Именно
они скрыли F-001…F-005, F-041…F-045 и баг с `#editor-area`.

- Хендлер, действие, воркер — `except Exception` только с
  `logger.exception(...)`.
- Опциональный `query_one` — `except NoMatches`, точечно.
- Вспомогательный метод из хендлера — пусть всплывает: диспетчер покажет.

### 9. Тесты

- Проверяй **эффект**, а не отсутствие исключения. Образец провала: четыре
  теста без `assert` пропустили P0 (F-034); `assert len(editors) > 0`
  проходил на пустом экране, пока `load_request` молча ничего не грузил.
- UI — `app.run_test()` + `pilot`, `await pilot.pause()` после каждого
  действия, влияющего на монтирование или воркер.
- Фейк повторяет **поверхность** настоящего объекта (все шесть методов
  `WorkerManager`), иначе тест воспроизводит ошибку кода.
- Отдельный класс дефектов — «тест зелёный, потому что сломанное молчит».
  Проверяй гвард мутацией: сломай правило руками и убедись, что тест упал.
  Так найдены беззубые проверки в `test_extensions_screen.py` (размер
  виджета вместо применённых деклараций) и три побайтно одинаковых
  снапшота (передавали объект вместо строки).
- Снапшоты: baseline без теста, тест без baseline и два одинаковых
  baseline — ошибка (`tests/snapshot/test_snapshot_inventory.py`).

### Чек-лист перед коммитом

```bash
uvx pre-commit run --files $(git diff --name-only HEAD)
uv run python tools/check_layers.py
uv run python tools/check_tui_css.py
uv run python tools/check_silent_except.py
scripts/run-tests.sh          # гейт tests/unit + маркер для Stop-хука
```

Плюс вручную, если правка про хендлеры: имя совпадает с
`MyMessage.handler_name`; `@on` не попал в миксин; новое сообщение где-то
постится; новая подписка снимается там, где заводится.

---

## Инварианты и подводные камни

- **Каждый экран имеет собственный `.tcss`** рядом с `.py`; файлы попадают в
  wheel через `[tool.setuptools.package-data]` (`*.tcss`, `**/*.tcss`) — без
  этого wheel собирается, но падает в рантайме с `FileNotFoundError`.
- **PRO-экраны условны**: `ReconScreen` и `ScannerScreen` импортируются только
  при наличии сабмодуля `pro`; иначе — fallback `scanner_unavailable.py`.
- Вкладки адресуются `tab_uid`, а не именем/индексом: переименование вкладки
  не должно терять сохранённое состояние.
- `StartStopWidget` — единственный источник логики Start/Stop.
  `set_paused(False)` возвращает «⏸ Pause» только если `_running`; иначе
  «▶ Start». Без этого `set_running(False)` + `set_paused(False)` (пара,
  которой экран синхронизирует таб) оставляла свежий таб «запущенным».
- **`AppMixin` — источник `err`/`_get_proxy`/`_get_proxy_api`/`_get_db_path`/
  `_send_to_decoder`.** Экран, вызывающий `self.err(...)` или
  `self._get_db_path()`, обязан иметь `AppMixin` в базах; гвард —
  `tests/unit/tui/test_app_mixin_surface.py`. Путь к БД — только
  `app.db_path`.
- **`ProxyService` приходит в `ProxyScreen` конструктором**, не присваиванием
  приватного поля снаружи (F-012); гвард —
  `test_proxy_service_injection.py` (AST-скан запрещает
  `<obj>._proxy_service =`).
- **AI-гейтованный контрол адресуется по id**, а не классом на весь экран, и
  видимость переприменяется при монтировании вкладки (F-022); гвард —
  `test_intruder_ai_visibility.py`.
- **Один циклер — `OptionCycler`**; в фильтр-барах он создаётся с
  `allow_empty=True` (опция 0 = «Any») и `suffix=" ▼"`.
- **Фильтры истории — `HistoryFilterBar`** (`ProxyFilterBar`, `WsFilterBar`):
  общая композиция, тоглы Scope/Comments, один `.tcss` с селекторами по
  базовому классу.
- **`on_resize` меняет класс, а не состояние пользователя** (F-027/ADR-7).
  `PentoolApp.on_resize` ставит `narrow` на активный `Screen` при ширине
  `< NARROW_BREAKPOINT` (80); что спрятать — решает CSS в `app.tcss`. Старый
  код звал `ProxyScreen.action_toggle_inspector()`, то есть переключал
  `_inspector_visible`: терминал сужался — инспектор исчезал навсегда, потому
  что обратно флаг никто не ставил. Гварды —
  `tests/unit/tui/test_responsive_layout.py`: реальный прогон с
  `resize_terminal` туда-обратно плюс AST-скан `on_resize` на запрет вызовов
  `action_toggle_inspector`/`action_hide_detail`.

## Связи

Зависит от [[api]], [[core]] и [[services]]. Опирается на [[deps/textual]] и
[[deps/textual-fastdatatable]]. PRO-экраны приходят из сабмодуля `pro`.

## Источник

Код `pentool/tui/`; аудит `docs/tui-audit/REPORT.md` (46 находок),
`DECISIONS.md` (ADR-1…ADR-14), `CONVENTIONS.md` (правила с обоснованиями),
`COMPONENTS.md` (каталог компонентов). Гварды — `tests/unit/tui/`,
`tests/snapshot/test_snapshot_inventory.py`, гейты — `tools/check_*.py`.
