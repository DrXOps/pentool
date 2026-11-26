# Аудит TUI — реестр находок и состояние

**HEAD на момент аудита:** `32e3624` (ветка `develop`), дата 2026-11-24.
**Объём:** `pentool/tui` — 101 файл Python, 25 323 строки; 53 `.tcss`, 3 008 строк.
Тесты: `tests/unit/tui` — 83 файла, 10 833 строки.

Документ отвечает на вопрос «что не так с кодом TUI и что с этим делать» и заменяет
собой утерянный `REPORT.md`, на который ссылались `CONVENTIONS.md` и `DECISIONS.md`.

---

## 0. Как читать этот документ

| Префикс | Что это |
|---|---|
| `F-001…F-049` | находки **первого** аудита. Их отчёт утерян; суть восстановлена по цитатам в `CONVENTIONS.md`/`DECISIONS.md`, статус перепроверен по коду. Где формулировка не восстанавливается однозначно — так и написано. |
| `F-100+` | находки этого аудита. |
| `C1…C10` | расхождение кода с конвенциями (дрейф). |
| `D1…D11` | дублирование: одно и то же поведение в нескольких местах. |
| `E1…E16` | архитектурные дефекты. |
| `S1…S6` | исправлено в этой сессии. |

Проверялось: чтением кода, поиском по AST, прогоном гейтов
(`check_tui_css`, `check_lazy_screens`, `check_silent_except`, `check_broad_except`,
`check_logging_policy`) и тестами. Каждое утверждение ниже имеет `путь:строка`;
номера строк соответствуют указанному HEAD.

---

## 1. Вердикт

1. **Конвенции первого аудита работают.** Четыре блокирующих гейта и восемь
   AST-гвардов живы, `except Exception: pass` — ноль, hex-цветов и CSS-строк в
   `.py` — ноль, ADR-7 (раскладка через CSS) и ADR-10 (сообщения вместо обхода
   дерева) внедрены по-настоящему. Это лучшая часть слоя, её надо расширять, а не
   переписывать.
2. **Расширяемость деградировала** — ровно по тому критерию, который важен
   владельцу. Каталог модулей был записан **пятью** независимыми списками, которые
   успели разойтись (вкладка «Dashboard» против подсказки «Dash»; четыре модуля из
   десяти показывали в строке подсказок «—»). Добавление модуля требовало правок в
   5–7 файлах. Исправлено в этой сессии (S1).
3. **Общей базы экрана нет.** Восемь экранов наследуются по-разному,
   `_refresh_header_now` продублирован 6 раз, `header_action` — 6 раз,
   `reload_from_project` — 2 несовместимые реализации. Это корень половины
   дублирования (E2).
4. **Два god-объекта:** `IntruderScreen` — 2 915 строк/110 методов,
   `ProxyScreen` — 2 363/100, `PentoolApp` — 2 603 строки, `on_mount` — 140 строк.
5. **HTTP- и WS-история Proxy — две копии одного конвейера** в одном файле, и копии
   уже разошлись (кэш метки, лживый докстринг). ~400 строк.
6. **Тесты сильные, но инварианты не запинены.** Именно поэтому дрейф и возник:
   «один ряд действий», «один каталог модулей», «экран не лезет в приватные поля
   app» ничем не проверялись. Часть гвардов фиксирует не то, что заявлено
   (`test_dialogs_unified` разрешает четыре формы Escape вместо запрета).
7. **Переписывать не нужно.** Нужны инкрементальные унификации; порядок и оценки —
   в разделе 8. Три механические вещи уже сделаны (S1–S4).

---

## 2. Реестр находок первого аудита (F-001…F-049)

Статус: **закрыт** — проверено по коду; **дрейф** — правило есть, код его нарушает;
**открыт** — не сделано.

| ID | Суть | Статус | Доказательство / что осталось |
|---|---|---|---|
| F-001 | `@on` в обычном классе-миксине не регистрируется: Textual собирает `_decorated_handlers` в `__init_subclass__` конкретного класса | закрыт | гвард `tests/unit/tui/test_handler_name_dispatch.py`; `@on` в `mixins/` — 0 |
| F-002 | подписки `EventBus.subscribe` живут дольше приложения | **дрейф** | 7 подписок снимаются в `action_quit` (`app.py:2571-2585`), хотя ADR-12 требует `_on_exit_app` |
| F-004 | экраны читают/пишут приватные поля App (`getattr(self.app, "_db_path", …)`) | **дрейф** | 11 мест, см. E3 |
| F-005 | «молчаливые» `except Exception` скрывали реальные ошибки | закрыт | `tools/silent_except_baseline.json` пуст (`{}`), гейт в pre-commit |
| F-006 | дублирующиеся `id` виджетов в разных экранах ломали фокус | закрыт | правило в `CONVENTIONS.md §5.3`; случай прокомментирован в `intruder/screen.py:1048-1055` |
| F-007 | `constants.py` заявлял «single source of truth», 53 из 61 константы не использовались | частично | ADR-9; дрейф — C9 (5 констант читает только линтер) |
| F-008 | 11 мёртвых CSS-селекторов в `.tcss` | закрыт | гейт `tools/check_tui_css.py` + самопроверка `test_check_tui_css.py` |
| F-009 | 615 `except Exception`, из них 286 → `pass` | закрыт частично | трещотки `check_silent_except` / `check_broad_except` / `check_logging_policy` держат потолок; 474 широких `except` остаются |
| F-012 | App сам создаёт инфраструктуру вместо внедрения зависимостей | **дрейф** | ADR-1; см. E4 |
| F-013 | соблюдение слоёв принималось на веру | **дрейф** | `tools/check_layers.py:26-37` проверяет только `tui → modules`; см. C4 |
| F-014 | экран продолжает писать в закрытую БД после переключения проекта | **открыт** | `project_manager.py:575-612` перезагружает экраны вручную; протокола нет (E6) |
| F-016 | копии хелперов (`err`, `_get_proxy`, `_get_db_path`, `_send_to_decoder`) в экранах | частично | ADR-13 + гвард `test_app_mixin_surface.py`; третья версия `_get_api` — `target/screen.py:282` |
| F-017 | 4 копии «вставить из буфера» | закрыт | `mixins/content_clipboard_mixin.py` |
| F-018 | уникальность `id` виджетов | закрыт | вместе с F-006 |
| F-019 | два Start/Stop виджета | закрыт | `widgets/start_stop_widget.py` удалён (файла нет) |
| F-020 | два «переключателя» (Cycler) | **дрейф** | `OptionCycler` единственный, но `ToggleButton` (`filter_bar_widget.py:36`) — вторая реализация той же идеи |
| F-021 | три фильтр-бара | частично | осталось два: `filter_bar_widget.py` (247) и `proxy_filter_bar.py` (291) |
| F-024 | 11 диалогов писали свою модальную обвязку | частично | `BaseDialog` есть, но 4 формы Escape и 2 вида кнопки — D7 |
| F-025 | CSS-строки в `.py` | закрыт | в `pentool/tui` — 0; гейт `test_css_hygiene.py` |
| F-027 | единственный `on_resize` переключал пользовательское состояние, а не раскладку | закрыт | ADR-7; `app.on_resize` (`app.py:1044-1070`) ставит класс `narrow` |
| F-034 | тест должен проверять эффект, а не отсутствие исключения | закрыт | образец — `tests/unit/tui/test_intruder_toolbar_wiring.py` |
| F-038 | дублирование CSS между экранами | частично | общие классы есть; `.tcss` на экран остаются |
| F-039 | мёртвые классы «на будущее» не удаляются | **дрейф** | `messages.ProxyClearHistory` (`messages.py:66`) жив, `app.py:51,2246` |
| F-041 | `ProxyDataTable.on_event` искал приватный `_open_context_menu` у предков | закрыт | ADR-10: `proxy_data_table.py:23-49,82-97` |
| F-043 | `Static.Clicked` не существует — обработчик мёртв | закрыт | удалён вместе с F-041 |
| F-044 | `DataTable.RowActivated` — нет такого в Textual 8 | закрыт | заменено на `CellSelected`/`RowSelected` |
| F-045 | `self.workers.cancel`, `get_worker`, `remove_worker` — методов нет в Textual | закрыт | используются `cancel_group`/`remove_worker` из актуального API |
| F-046 | `Config.add_observer` живёт дольше приложения | закрыт | снимается в `_on_exit_app` (`app.py:2506-2511`) |
| F-047 | шесть экранов звали `self.err(...)` без `AppMixin` в базе | закрыт | ADR-13 + гвард `test_app_mixin_surface.py` |
| F-048 | техдетект запускался `asyncio.create_task` без группы и отмены | частично | ADR-11; `run_worker` с `group=` — 16 из 68 |
| F-049 | копии `_get_proxy/_get_proxy_api/_get_db_path` в экранах | частично | вместе с F-016 |

Идентификаторы F-003, F-010, F-011, F-015, F-022, F-023, F-026, F-028…F-033,
F-035…F-037, F-040, F-042 в документах не цитируются — их содержание
восстановить нельзя.

---

## 3. Дрейф конвенций (C)

**C1. ADR-2 не выполнен:** `messages.ProxyClearHistory` (`messages.py:66`) не постится
никуда; поля `req: object` остались (`messages.py:21,53,62,81,88`) — типизация через
`ImportGuard`/`TYPE_CHECKING` не сделана.

**C2. ADR-3 искажён комментарием:** `mixins/events_handlers.py:5-12` и
`app.py:1894-1897` дословно повторяют вывод, который ADR-3 объявляет неверным
(«поэтому держим `@on` в app.py»). Код правило не нарушает — нарушает обоснование,
которое следующий агент прочитает как инструкцию.

**C3. ADR-12 выполнен наполовину:** `Config.remove_observer` снимается в
`_on_exit_app`, а 7 подписок `EventBus` — в `action_quit`. `_on_bus_scan_progress`
(`app.py:2469-2471`) — пустой обработчик, подписанный ни для чего.

**C4. Проверка слоёв слабее заявленной:** `tools/check_layers.py:26-37` для `tui`
запрещает только `pentool.modules`; `tui → core`, `→ storage`, `→ services`, `→ proxy`
не проверяются, хотя `CONVENTIONS.md §4` утверждает обратное, а `tui → core.db_schema`
используется по-настоящему (E7). Докстринг того же файла (`check_layers.py:9`)
противоречит его таблице.

**C5. §5 вне области гварда:** хендлеры, действия и воркеры обязаны писать трейсбек —
гвард покрывает их, но EventBus-обработчики и вспомогательные методы живут по старому
правилу: из 472 `except Exception` в слое ≈290 заканчиваются однострочным
`logger.debug("…%s", exc)` (`app.py:2330,2339,2457,2464,2479,2502`,
`mixins/proxy_runtime.py:164,176,239,263`).

**C6. §5 (трещотка) — подтверждено:** узкие `except ValueError/re.error/NoMatches/OSError`
с `pass` остались в 7 местах, это соответствует букве конвенции.

**C7. §6.2 «hex-цветов нет» верно только для CSS:** `widgets/keyhintbar.py:15-26`
держит 10 hex-цветов в Python (Rich-markup), которые не переключаются темой и не
видны ни одному CSS-гейту.

**C8. ADR-5 (каталог компонентов) устарел:** `StartStopWidget` в таблице есть, файла
нет; «единственный переключатель» — на самом деле два (`ToggleButton`).

**C9. ADR-9 держит украшение:** `constants.py:19,22,24,25,26` импортируются только
`tools/check_lazy_screens.py` и `pro/.../reports_pro.py`; тест
`test_constants_are_used.py:28-50` считает импорт из `tools/` доказательством
использования. Плюс две формы одного id: `"#screen-proxy"` в константах против
`screen_lifecycle.screen_id()` без `#`.

**C10. Документация ссылалась на несуществующие файлы** — этот документ и `SUMMARY.md`
восстанавливают ссылки; нумерация F-001…F-049 — см. раздел 2.

---

## 4. Дублирование (D)

Счёт: **не менее 27 имён методов** с самостоятельными реализациями в 2–6 файлах
(AST-сверка), из них ~17 — одно и то же поведение по смыслу.

| ID | Что дублируется | Где | Где должно жить | Бласт-радиус |
|---|---|---|---|---|
| D1 | каталог модулей: 5 списков | `module_tabs.py:19-35`, `hotkeys/defaults.py:44-68`, `screen_registry.py:26-37`, `app.py:1238`, `project_manager.py:29` | **сделано:** `pentool/tui/module_catalog.py` (S1) | 6 файлов |
| D2 | HTTP- и WS-история Proxy: ~9 пар методов, ~400 строк | `proxy/screen.py:646-919,1115-1322,1379-1449,1484-1494` | `widgets/history_panel.py::HistoryTab(source)` | 1 файл + 6 тестов |
| D3 | механика вкладок: 3 реализации rename | `screens/base.py:19-123`, `widgets/tab_panel.py:496-565`, `repeater/screen.py:593-641` | один владелец — `TabbedContentPanel` | 4 файла |
| D4 | `SettingsScreen`: 21 копия «прочитать виджет → сравнить → сохранить» | `settings/screen.py:562-856` | `FieldSpec` + `SettingsSection.collect()/fill()` | 1 файл + 1 новый |
| D5 | 6 путей уведомлений | `app.py:284-304`, `mixins/notifications.py:23-89`, `module_tabs.py:117-155`, `repeater/screen.py:149-159,1111-1118` | `NotifyMixin` в базе экрана | 6 файлов |
| D6 | старт/стоп прокси: 4 варианта с одинаковым эпилогом | `mixins/proxy_runtime.py:91-270` | `_after_proxy_transition(running)` | 1 файл |
| D7 | диалоги: 4 формы Escape, 2 вида кнопки, 4 копии `action_cancel` | `dialogs/*` | `FormDialog` | 11 файлов |
| D8 | загрузка файла: 4 несовместимых пути (один — синхронный в UI-потоке) | `intruder/screen.py:2168-2293`, `payload_drop_zone.py:47-52`, `comparer/screen.py:115-130`, `sequencer/screen.py:334-353` | `mixins/file_io.py` + `PayloadFileLoader` | 5 файлов |
| D9 | рендер unified-diff: 2 реализации, разошлись в деталях | `widgets/diff_panel.py:33-57`, `comparer/screen.py:174-204` | `diff_panel.render_diff()` | 2 файла |
| D10 | `_refresh_header_now` — 6 копий | `dashboard:557`, `utils:152`, `repeater:223`, `intruder:908`, `sequencer:163`, `proxy:549` | `AppMixin.refresh_header()` | 7 файлов |
| D11 | извлечение host/URL — 10+ мест | `mixins/auto_scope.py:74-95` и др. | `utils/urls.host_of()` | 8 файлов |

---

## 5. Архитектурные дефекты (E)

**E1 (P1). Два механизма «ряд действий модуля».** Контракт `HeaderSpec`
(`header.py:67-81`) реализуют 6 локальных экранов и 2 PRO-экрана; `Target`
(`target/screen.py:160-188`), `Decoder` (`decoder/screen.py:46-52`) и `Comparer`
(`comparer/screen.py:44-50`) строят свой `Toolbar` и обрабатывают `ToolbarButton.Pressed`.
Диспетчеризация тоже разная: `if/elif` в `header_action` (6 копий) против `@on(..., "#btn-…")`.
Следствие: заголовок Target визуально и поведенчески отличается от остальных модулей.

**E2 (P1). Нет общей базы экрана.** `ComparerScreen(ContentClipboardMixin, AppMixin, Widget)`,
`TargetScreen(…, AutoSaveMixin, AppMixin, Widget)`, `RepeaterScreen(AutoSaveMixin,
BaseModuleScreen, RequestContextMenuMixin, AppMixin)` — восемь разных MRO. Сквозные
обязанности нигде не собраны: `reload_from_project` (`intruder:1228-1250` принимает
`db_path`, `repeater:530-560` делает `switch_db` сам), `_save_current_tab_state`,
`_load_tabs_from_db`, `_setup_tooltips`, `on_worker_state_changed`, `_get_api`.

**E3 (P1). Экран мутирует App через приватные поля.** `self.app._project_path = path`
(`dashboard/screen.py:1041`), чтение `_project_path`/`_cfg` там же, вызов приватного
`_switch_project_db` через `getattr` (`682,982,1008`), `sequencer:215` читает
`self.app._proxy_api`, `target:698` — `self.app._proxy`. Всего 11 обращений.

**E4 (P2). `PentoolApp` — god object.** 2 603 строки, `on_mount` (`518-659`) делает
20 несвязанных вещей. Мёртвый слой делегирования: `app.py:2393-2435` — 15 обёрток над
`self._pm`, из них `_do_save_project_json`/`_do_load_project_json` не вызываются нигде,
а `_collect_spider_sessions`/`_reload_project_screens`/`_init_new_db`/
`_switch_storage_db`/`_open_project_sequence` вызывают только сами себя; парные методы
`ProjectManager` помечены «kept for compatibility with app.py». Плюс monkey-patch
`textual.screen.Screen._forward_event`/`_handle_mouse_move` в рантайме (`383-443`) и
`Checkbox.BUTTON_*` при импорте (`85-87`). Второй механизм разрешения экрана —
`_get_cached_screen` (`1864-1888`) рядом с `LazyScreenManager`.

**E5 (P2). Проверка лицензии была копипастой на два блока** — `app.py:1287-1342`.
**Исправлено** (S2): одна проверка по каталогу.

**E6 (P2). `ProjectManager` знает приватные поля каждого экрана.**
`project_manager.py:575-612` — `match module_id` с вызовами `_reload_from_storage`,
`_scanner_api`, `_get_or_create_api`, `_populate_from_db`, `_load_findings_worker`,
`_clear_scan_logs`; `614-647` — `_target_api.save()`, `sitemap._scope_hosts.clear()`.
Всё под `# type: ignore[attr-defined]` (в слое 188 таких подавлений).

**E7 (P2). Экран читает/пишет БД в обход `ProxyService`** (`proxy/screen.py:1955-2041`,
прямые импорты `pentool.core.db_schema`). Второй путь к той же БД, не видящий
переключения проекта.

**E8 (P2). Бизнес-логика в виджетах.** `widgets/intercept.py` (347 строк) — на самом
деле миксин: очередь перехвата, Forward/Drop, работа с редактором, правка приватных
полей `TextArea` (`209-210`). `diff_panel.py:33-57` сам вызывает движок сравнения.
`payload_drop_zone.py:47-52` сам читает файл. `activity_indicator.py:144` спрашивает
`is_mcp_busy()`.

**E9 (P2). Блокирующий ввод-вывод в обработчиках:** `sequencer/screen.py:341,410`,
`comparer/screen.py:122`, `intruder/screen.py:3031`, `payload_drop_zone.py:50`.
При том что сам Intruder умеет правильно (`2200,2219-2220` — `run_in_executor`).

**E10 (P2). Мёртвый код ~600 строк:** `widgets/custom_notify.py` (186 + 70 tcss,
не импортируется нигде и называет себя «единственной системой уведомлений»),
`widgets/hintbar_base.py` (39 + 9), `messages.ProxyClearHistory`,
`app.py:2416-2435`, `tab_panel._is_stale`/`set_generation`/`_make_default_state`/
`set_default_state_factory`, `mixins/safe_query.safe_notify`.

**E11 (P2). Стрелка сортировки ▲/▼ не появлялась никогда.** `_sort_table_sql`
передавал `None` вместо таблицы, `AttributeError` глотался широким `except`.
**Исправлено** (S3), добавлены два теста, которые проверяют саму стрелку.

**E12 (P2). Подсказки внизу пусты для 4 из 10 модулей.** Группы хоткеев привязаны к
старым id (`decoder/comparer/sequencer`), а модули после слияния — `utils/extensions/
recon/settings`; `registry.get_entries(module)` возвращал `[]` → строка «—».
**Исправлено** (S1): группы берутся из каталога, при их отсутствии показываются
глобальные клавиши вместо пустоты.

**E13 (P2). Одно действие — два входа:** `action_toggle_intercept` (`app.py:1795-1804`
и `widgets/intercept.py:333-342`), `flash` (D5), `action_toggle_proxy`
(`proxy/screen.py:1861-1872` + `proxy_runtime.py:49-73`).

**E14 (P3). Тема применяется из 6 мест** (`app.py:619-628,2302-2310`,
`settings/screen.py:496-560`); комментарий `app.py:2299-2301` сам признаёт двойной рендер.

**E15 (P3). Экран цепляется за слоты заголовка App по позиционному id:**
`repeater/screen.py:127-139` возвращает `self.app.query_one("#hdr-state-2")`.

**E16 (P3). Глобальные побочные эффекты при импорте:** `mixins/auto_scope.py:14`
(`log.setLevel(logging.INFO)` на весь процесс), `app.py:85-87` (мутация `Checkbox`),
`hotkeys/defaults.py:194-203` (регистрация в синглтоне при импорте).

---

## 6. Тесты

**Есть (сильная сторона):** 83 файла / 10 833 строки в `tests/unit/tui`, плюс
`tests/integration/test_tui_events.py` и `tests/perf/tui_deep.py`. Восемь AST-гвардов
архитектуры кусаются и проверены мутацией: `test_handler_name_dispatch`,
`test_app_mixin_surface`, `test_on_selectors_resolve`, `test_query_one_in_handlers`,
`test_no_matches_is_precise`, `test_handler_exceptions_logged`,
`test_silent_except_ratchet`, `test_css_hygiene` (+`test_check_tui_css`).

**Не покрыто:**

1. `pentool/tui/header.py` — 0 тестов на контракт заголовка; поэтому E1 ничем не ловится.
2. `project_manager.py` (714 строк) — 0 прямых тестов.
3. `screens/utils/screen.py`, `screens/proxy/context_menu.py`, `screens/base.py` — 0.
4. 13 из 16 диалогов — 0 (`file_selector` 247 строк, `scope_dialog` 241,
   `match_replace_dialog` 232).
5. `mixins/auto_scope.py` (248, с сетевым кодом), `ai_sync`, `dialog_cancel`,
   `safe_query` — 0.
6. `widgets/intercept.py` (347, Forward/Drop) — 0 прямых тестов.
7. `filter_bar_widget.py` (247) — 0 прямых тестов.

**Тесты, фиксирующие не то, что заявлено:** `test_dialogs_unified.py:61-64`
перечисляет четыре формы Escape как допустимые; `test_sortable_table_mixin.py` не
проверял стрелку (исправлено, S3); `test_constants_are_used.py:28-50` считает импорт
из `tools/` использованием.

**Нет гвардов на:** отсутствие `Toolbar(` в `compose()` экрана, `self.app._*` из
экранов, соответствие id модуля группе подсказок (добавлен, S1), обязательный `group=`
у долгоживущих `run_worker`, `@on` вне App/Widget.

**Предупреждение в прогоне:** `RuntimeWarning: coroutine 'TargetScreen._do_save_sitemap'
was never awaited` — приходит из teardown pilot-тестов при отмене воркера
(`target/screen.py:240-251` закрывает корутину, если воркер не принят). В рантайме
не воспроизводится; занесено как шум тестов, не как дефект продукта.

---

## 7. Исправлено в этой сессии

### S1. Каталог модулей (закрывает D1, E5, E12, часть C9)

Новый `pentool/tui/module_catalog.py` — одна запись `Module(id, label, short, hotkey,
basic, free, license_feature, reloadable, hints)` на модуль. Производными стали:
`widgets/module_tabs.MODULES` и `BASIC_MODULES`, `hotkeys/defaults._MODULE_ENTRIES`,
`PentoolApp._FREE_MODULES`, `project_manager._RELOADABLE_MODULES`, подписи в
`keyhintbar.module_label`, группы подсказок. `SCREEN_MAP` остаётся в
`screen_registry` (нужны классы), но тест `test_module_catalog.py` проверяет, что
каталог и реестр экранов совпадают.

Заодно: `set_scanner_locked` → `set_module_locked(module_id, locked)` — блокировка PRO
больше не привязана к Scanner; `_refresh_scanner_tab_lock` → `_refresh_tab_locks`
(цикл по каталогу).

### S2. Проверка лицензии — один раз вместо двух копий (E5)

`_switch_to` спрашивает фичу у каталога (`license_feature`) и обрабатывает её одним
блоком: fail-closed при ошибке чтения лицензии, отдельный текст для «ключ есть, фичи
нет».

### S3. Стрелка сортировки (E11)

`_update_sort_arrows` получает реальную таблицу; `except` сужен до
`AttributeError/IndexError`; два новых теста проверяют «▲ на активной колонке» и
«▼ после второго клика».

### S4. AI-задача `discovery` (F-100, новый)

`pro/.../ai_discovery/{subdomain,endpoint,param_fuzzer,runner}.py` вызывают
`backend.generate("discovery", …)`, а в реестре задач её не было: `MCPBackend.generate`
возвращал `None` с записью в лог, и **ИИ-часть Recon не выдавала ни одного кандидата**.
Задача зарегистрирована в `pentool/services/ai/prompts.py`; гвард
`tests/unit/services/test_ai_task_registry.py` сканирует все `.generate("<task>")` в
`pentool/` и `pro/pentool/` и падает на незарегистрированном имени.

### S5. Команды, которых нет (F-101, новый)

В интерфейсе и сообщениях фигурировали `pentool license trial`, `pentool license
activate <key>`, `pentool license status` — таких команд нет (в CLI нет группы
`license`, `python -m pentool license trial` → exit 2). Заменено на реальный путь:
Settings → License. Затронуто: `module_tabs` (tooltip), `app._switch_to` (два
сообщения), `scanner_unavailable.py`, `cli/scan_runner.py`, `core/plugin_manager.py`,
`core/license.py` (два текста).

### S6. Ссылка на цены (F-102, новый)

`settings/screen.py:279` вела на `https://pentool.pro/pricing` (404 на GitHub Pages).
Теперь `/pricing.html`, и на сайте добавлен редирект `/pricing` → `/pricing.html` для
уже выпущенных сборок.

---

## 8. План унификации

Каждый шаг самостоятелен, обратим и проверяем. Оценки — рабочие дни одного человека.

**Шаг 0. Санитарный: удалить мёртвый код (0,5 д).**
`widgets/custom_notify.py` + `.tcss`, `widgets/hintbar_base.py` + `.tcss`,
`messages.ProxyClearHistory` (+ `app.py:51,2246-2257`), `app.py:2416-2435` и парные
`ProjectManager._switch_storage_db`/`_open_project_sequence`, `tab_panel._is_stale`/
`set_generation`/`_make_default_state`/`set_default_state_factory`,
`safe_query.safe_notify`, мёртвые константы `constants.py`.
Проверка: гейты + `pytest tests/unit/tui`. Риск низкий.

**Шаг 1 — сделан (S1).** Каталог модулей.

**Шаг 2. `ModuleScreen` — общая база экрана (3–4 д).**
`header_spec/header_action` через таблицу `ACTIONS`, `refresh_header()`,
`notify/flash`, `ProjectReloadable` (`reload_from_project`, `reset_for_new_project`,
`close_storage`), `_get_api()`. Перевести 8 экранов по одному, начиная с простых
(Decoder → Comparer → Sequencer → Dashboard → Target → Repeater → Proxy → Intruder).
Снимает D10/E2/E6 и половину D3.

**Шаг 3. Один ряд действий = `HeaderSpec` (2 д).** Мигрировать Target, Decoder,
Comparer; удалить `Toolbar(...)` из их `compose()`; добавить AST-гвард.
Закрывает E1.

**Шаг 4. Вкладки: один владелец (2–3 д).** Rename-механика — только
`TabbedContentPanel`; `BaseModuleScreen` удалить; `_save_current_tab_state`/
`_load_tabs_from_db` — в панель. Закрывает D3.

**Шаг 5. Распил `IntruderScreen` (3–4 д).** `IntruderPayloadSources`,
`IntruderResultsView`, `IntruderAttackRunner`, дескриптор для 8 пар свойств вкладок.
Цель — класс ≤900 строк.

**Шаг 6. Распил `ProxyScreen` + слияние HTTP/WS (3–4 д).** `HistoryTab(HistorySource)`,
контекстное меню — в существующий миксин, настройки проекта — в `ProxyService` (E7).
Закрывает D2/E7.

**Шаг 7. Диалоги и формы (2 д).** `FormDialog`: `FieldSpec[]`, OK/Cancel,
`action_cancel`; удалить 4 `action_cancel`, 6 переопределений Escape, 4 `on_btn_cancel`;
переписать `test_dialogs_unified` в запрет. Закрывает D7.

**Шаг 8. `SettingsScreen` на декларативные секции (1–2 д).** `SettingsSection(
specs).collect()/fill()`. Закрывает D4.

**Шаг 9. Ввод-вывод, уведомления, транспорт (1–2 д).** `read_text_async`,
`NotifyMixin`, `host_of()`, `_after_proxy_transition`. Закрывает D5/D6/D8/D9/D11.

**Шаг 10. Документация и гварды (1 д).** Обновить ADR-2/3/5/9/12 по факту (C1–C3, C8,
C9), расширить `check_layers` на `tui → core/services/storage` (C4), добавить гварды:
нет `Toolbar(` в `compose()` экрана, нет `self.app._` в `screens/`, `run_worker` с
`group=` у долгоживущих задач, `@on` только в App/Widget.

**Отдельно: `pentool license {activate,deactivate,status,trial}` (1 д).** Функции
активации/деактивации/переноса в `core/license.py` есть, `start_trial()` не вызывается
ниоткуда, а интерфейс и сообщения годами ссылались на несуществующие команды (S5).
Либо реализовать группу CLI (проще: обертки над существующими функциями + тесты), либо
перестать упоминать её где-либо — сейчас выбрано второе.

---

## 9. Что не трогать

1. `screen_lifecycle.py` (267 строк) — образец: чистая `plan_switch`,
   `ScreenHost(Protocol)`, `LazyScreenManager`, тесты на фейковом хосте.
2. `header.py` как контракт — правильная форма; проблема не в нём, а в трёх экранах
   вне контракта.
3. `ContentPanel.ROLES` + `test_panel_roles.py` — роль вместо перечисления кнопок,
   `ValueError` на неизвестную роль.
4. Табличный слой: `table_factory.make_table`, `ArrowBackendDataTable.fit_columns`,
   `SortableTableMixin` как единственная точка сортировки.
5. Единая таблица хоткеев с рендером подсказок из реестра (теперь с каталогом).
6. Четыре блокирующих гейта и самопроверяющиеся гварды — расширять, не заменять.
7. Дисциплина исключений там, где она механизирована: узкие `except` с комментарием
   «что произойдёт, если проглотить».
8. ADR-7 и ADR-10 — внедрены по-настоящему.
9. Ленивое монтирование экранов, `gc.freeze`, кэш слотов заголовка: в шагах 5–6 эти
   решения сохранять, а не упрощать.
