# Закрыто

Одна строка на задачу: дата · что · чем проверено. Пункты отсюда удаляются из планов —
в плане остаётся только несделанное.

| Дата | Что закрыто | Чем проверено |
|---|---|---|
| 2026-11-23 | ТУИ: мёртвый код удалён (10 файлов, −377 строк) | `tests/unit` + `check_lazy_screens` |
| 2026-11-23 | ТУИ: каталог модулей один, остальные — производные | факт `tui.module_catalog` |
| 2026-11-24 | ТУИ: шесть копий `_refresh_header_now` → `AppMixin.refresh_header` | факт `tui.header_refresh` |
| 2026-11-24 | ТУИ: `ModuleScreen` + `ACTIONS` вместо цепочек `if action_id ==` | факт `tui.action_row` |
| 2026-11-25 | ТУИ: `ProjectReloadable` — менеджер не трогает приватные поля экранов | факт `tui.project_reload` |
| 2026-11-25 | ТУИ: переименование вкладок — один `TabRenameMixin` (4 копии → 1) | факт `tui.tab_rename` |
| 2026-11-25 | Intruder: payload-файлы — один парсер и один загрузчик | факт `intruder.payloads` |
| 2026-11-25 | Intruder: рендер результатов вынесен из экрана | факт `intruder.results_view` |
| 2026-11-25 | Intruder: поля активной вкладки — один дескриптор вместо 8 пар | факт `intruder.tab_fields` |
| 2026-11-25 | Intruder: жизненный цикл атаки вынесен в `attack_runner.py` | факт `intruder.attack_runner` |
| 2026-11-25 | Proxy: счётчик истории, пагинация, выбор строки, панель деталей | факт `proxy.history_counter` |
| 2026-11-26 | Краши: `_TabId`, гонка вкладок (`ValueError`), passive в сканере | `test_crash_regressions.py`, лог сервера |
| 2026-11-26 | Старт: пустые кнопки шапки больше не мигают | `test_startup_paint.py` |
| 2026-11-26 | Beautify: в панели, из шапки убран | `test_panel_beautify.py` |
| 2026-11-26 | Intruder: настройки и кнопки вкладок — одна строка | `test_intruder_toolbar_wiring.py` |
| 2026-11-26 | Сканер: меню «⋯» убрано, Passive/False+ в строке действий | PRO-сборка + `test_crash_regressions.py` |
| 2026-11-26 | Comparer: инструменты снова видны | CSS-правило + `check_tui_css` |
| 2026-11-26 | Target: карта сайта не съезжает на пол-экрана | `test_target_layout.py` |
| 2026-11-26 | Копипаст из WSL: `clip.exe`/PowerShell, round-trip проверен | `test_wsl_clipboard.py` |
| 2026-11-26 | Шапка: гвард «шапка показывает то, что объявляет экран» | `test_header_matches_spec.py` |
| 2026-11-26 | Админка: параллельная загрузка, обратная связь входа, массовые действия | живой деплой `license.pentool.pro/admin` |
| 2026-11-26 | Профилирование: замеры горячих путей, отчёт с числами | `tests/perf/tui_hotpaths.py` |
| 2026-11-26 | Сканер: пассивный режим прочёсывает историю прокси при включении (pro `681c542`) | `test_passive_replay.py` |
| 2026-11-26 | Сканер: дублирующий тулбар убран (N1) | grep: в PRO-сканере нет `id="toolbar"` |
| 2026-11-26 | WS-счётчик истории: виджет есть, идёт через `HistoryCounter` (N4) | `proxy/history_view.py` + `test_proxy_history_paging.py` |
| 2026-11-26 | Удалены устаревшие P3: `docs/audit/README.md` и права `docs/i18n/**` (папок больше нет) | `check_docs` |
