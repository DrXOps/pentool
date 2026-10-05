# План: Унификация TUI

## 1. Исполнительное резюме

Текущее состояние TUI — 12 экранов, каждый со своим стилем кода.
Сделано: StartStopMixin внедрён в Intruder, Scanner, Recon.
Осталось: убрать мёртвый код, стандартизировать toolbar/DataTable/RichLog/ProgressBar.

## 2. Сделано (закрытые пункты)

- StartStopMixin создан и внедрён в IntruderScreen, ScannerScreen, ReconScreen
- @on хендлеры btn-start/btn-stop работают через явное объявление в каждом экране
- ReconScreen переведён на btn-start/btn-stop (было recon-start/recon-stop)
- ActionIndicator Recon: фикс ложного мигания (MessagePump._running)
- Input compact=True — это конвенция для всех Input в toolbars (44 места). Settings — исключение (multiline)
- Прогресс бары есть на Intruder, Sequencer, Scanner — по необходимости
- DataTable в проекте — одна база: ArrowBackendDataTable (виджет-обёртка, не 3 разных). IntruderResultsTable и ProxyDataTable наследуют его.

## 3. Остаётся сделать

### 3.1 Мёртвый код

- `toolbar_helper.py` — `build_toolbar()` используется только SequencerScreen.
  Решение: удалить, дублирующую логику перенести в toolbar.py.

- `pentool/tui/widgets/filter_bar_widget.py` — проверить, используется ли, не заменил ли его IntruderFilterBar.

### 3.2 CSS — дублирование

Каждый экран имеет свой .tcss с повторяющимися правилами:

```tcss
/* Повторяется в 8 из 11 TCSS файлов */
ScreenName #toolbar {
    height: 2;
    layout: horizontal;
    border-bottom: solid $primary-darken-2;
}
```

Решение: вынести в app.tcss как `.toolbar` класс, перевести compose экранов на класс.

### 3.3 Toolbar виджет

В `pentool/tui/widgets/toolbar.py` уже создан класс Toolbar с хелперами:
- `ToolbarButton(...)` — кнопка
- `Toolbar.sep()` — сепаратор
- `Toolbar.label(...)` — лейбл
- `Toolbar.input(...)` — Input с compact=True
- `Toolbar.progress()` — ProgressBar

Решение: внедрить Toolbar compose во все экраны.

### 3.4 RichLog — шаблон

`RichLog(id="...", highlight=True, markup=True, wrap=True, max_lines=100)` в 4+ местах.

Решение: вынести конфигурацию в общий стиль .screen-log или хелпер.

### 3.5 DataTable — способ добавления колонок

Везде используется `ArrowBackendDataTable.set_data(arrow_table)` для полной перестройки.
3 способа задания колонок:
1. В конструкторе: `ArrowBackendDataTable(columns=[...])`
2. Через `table.add_column(...)` в on_mount
3. Через `table.add_columns(*names)` в process_compose

Решение: проверить и стандартизировать на одном подходе.

### 3.6 ProgressBar — не унифицирован

На экранах где есть:
- Intruder: ручной `ProgressBar(total=100, id="attack-progress", ...)`
- Sequencer: ручной
- Scanner: ручной

Решение: использовать `Toolbar.progress()`.

### 3.7 RichLog — одинаковый набор параметров

На экранах где RichLog используется как лог:
- Repeater, Proxy, Scanner, Recon — одни и те же параметры

Решение: вынести в хелпер или общий класс.

## 4. Приоритет

1. Удаление `toolbar_helper.py`
2. Внедрение `Toolbar` compose из toolbar.py
3. CSS — общий `.toolbar` в app.tcss
4. RichLog — стандартный конфиг
5. DataTable — единый подход к колонкам
6. ProgressBar — через Toolbar.progress()