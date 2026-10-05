# TUI Audit — полная ревизия структуры экранов и виджетов

## 1. Таблица всех экранов

| Экран | Тип | Toolbar ID | Start/Stop | TCSS (строк) | @on vs хендлер |
|---|---|---|---|---|---|
| **Intruder** | FREE | `#toolbar` | ✅ btn-start/btn-stop | 273 | @on |
| **Repeater** | FREE | `#top-bar` | ❌ (Send/Cancel) | 75 | @on |
| **Proxy** | FREE | `#toolbar` | ❌ (Proxy/Intercept toggle) | 161 | @on |
| **Dashboard** | FREE | (нет) | ❌ | 218 | @on |
| **Decoder** | FREE | `#dec-toolbar` | ❌ | 94 | @on |
| **Comparer** | FREE | `#cmp-toolbar` | ❌ | 78 | @on |
| **Sequencer** | FREE | `#seq-toolbar` | ✅ btn-seq-capture/btn-seq-stop | 130 | @on |
| **Target** | FREE | `#toolbar` | ❌ | 43 | @on |
| **Settings** | FREE | (Vertical) | ❌ | 119 | @on |
| **Extensions** | FREE | (нет) | ❌ | 22 | @on |
| **Scanner** | PRO | `#toolbar` | ✅ btn-start/btn-stop | 249 | @on |
| **Recon** | PRO | `#recon-toolbar` | ✅ recon-start/recon-stop | 109 | on_toolbar_button_pressed |

## 2. Паттерны кнопок Start/Stop/Resume

### Текущая реализация на 3 экранах

| Экран | ID кнопок | Механика | Флаги | Пауза | _set_running_state |
|---|---|---|---|---|---|
| **Intruder** | `btn-start`, `btn-stop` | Start→Pause→Resume | `_attack_running`, `_paused` | ✅ (worker.pause/resume) | ✅ `_set_running_state(running)` |
| **Scanner (PRO)** | `btn-start`, `btn-stop` | Start→Pause→Resume | `_scanning`, `_paused` | ✅ (svc.request_stop + ui) | ✅ `_set_scan_running_ui()` / `_set_scan_pause_ui()` |
| **Recon (PRO)** | `recon-start`, `recon-stop` | Start→Pause→Resume | `_running`, `_paused` | ✅ (worker.cancel + rerun) | ✅ `_set_running_state(running)` |

### Проблемы Recon:
- Использует **другие ID** кнопок (`recon-start` вместо `btn-start`) — невозможно переиспользовать общий хендлер
- Использует `on_toolbar_button_pressed` вместо `@on(ToolbarButton.Pressed, "#btn-start")` — единый хендлер вместо декораторов (единственный экран в проекте)
- `_set_running_state` не работает — вероятно `query_one("#recon-start", ToolbarButton)` падает, так как в widgets импорте нет ToolbarButton (проверь — в compose виджет есть, но может не матчиться селектор)
- **Recon Log не виден** — `#recon-right-sidebar` с `width: 40` не отображается, возможно из-за конфликта layout у `#recon-body`

## 3. Единая конвенция кнопок

Все экраны с Start/Stop/Resume должны использовать **один и тот же ID и один паттерн**:

| Кнопка | ID | Label (состояния) |
|---|---|---|
| Start/Pause/Resume | `btn-start` | `▶ Start` / `⏸ Pause` / `▶ Resume` |
| Stop | `btn-stop` | `■ Stop` |
| Cancel | `btn-cancel` | `✖ Cancel` |
| Send | `btn-send` | `⚡ Send` |

### Единый протокол:
```python
# Во всех классах:
_running: bool = False  # единое имя
_paused: bool = False

def _set_running_state(self, running: bool) -> None:
    """Единый метод обновления кнопок при старте/стопе."""
    btn_start = self.query_one("#btn-start", ToolbarButton)
    btn_stop = self.query_one("#btn-stop", ToolbarButton)
    if running:
        btn_start.label = "⏸ Pause"
        btn_start.variant = "warning"
        btn_stop.disabled = False
    else:
        btn_start.label = "▶ Start"
        btn_start.variant = "success"
        btn_stop.disabled = True
        self._paused = False

# Во всех экранах — @on декораторы:
@on(ToolbarButton.Pressed, "#btn-start")
def on_btn_start(self, _: ToolbarButton.Pressed) -> None:
    if self._paused:
        self.action_resume()
    elif self._running:
        self.action_toggle_pause()
    else:
        self.action_start()

@on(ToolbarButton.Pressed, "#btn-stop")
def on_btn_stop(self, _: ToolbarButton.Pressed) -> None:
    self.action_stop()
```

## 4. CSS-дубликаты — полный список

### 4.1 Повторяющийся `#toolbar {` стиль (4 экрана + 3 кастомных)

Базовый паттерн (почти идентичен в Intruder, Proxy, Target, Scanner):

```tcss
ScreenName #toolbar {
    height: 2;
    background: $panel;
    padding: 0 1;
    align: left middle;
    layout: horizontal;
    border-bottom: solid $primary-darken-2;
    overflow: hidden hidden;
}
```

Дублируется в **7 из 12 файлов** TCSS. Единственное решение — вынести в единый CSS-класс:

```tcss
/* В toolbar_button.tcss или в отдельный toolbar.tcss */
.toolbar {
    height: 2;
    background: $panel;
    padding: 0 1;
    align: left middle;
    layout: horizontal;
    border-bottom: solid $primary-darken-2;
    overflow: hidden hidden;
}
```

Тогда compose:
```python
with Horizontal(id="toolbar", classes="toolbar"):
    ...
```

Без дублирования CSS на каждом экране.

### 4.2 `toolbar-sep` — продублирован в 9 из 12 TCSS файлов

```tcss
.toolbar-sep { width: auto; }
```

Этот класс уже есть в `toolbar_button.tcss` (глобальный селектор `.toolbar-sep`). Но каждый экран дублирует его с комментарием "toolbar-sep fix — Static does not inherit..."

**Решение:** удалить из всех экранов. Глобальный селектор в `toolbar_button.tcss` достаточно:

```tcss
/* toolbar_button.tcss — уже есть */
.toolbar-sep {
    width: auto;
    color: $primary-darken-2;
}
```

### 4.3 Дубликаты стилей `TabPane`, `TabbedContent` и таблиц

Почти все экраны с таблицами повторяют:

```tcss
ScreenName TabbedContent { height: 1fr; }
ScreenName TabPane { height: 1fr; padding: 0; }
ScreenName #some-table { height: 1fr; }
```

### 4.4 Панели с label (Scanner .tab-log-label, Proxy .panel-title, Recon .recon-panel-label)

Повторяющийся паттерн заголовков панелей:
- Scanner `.tab-log-label`: `height: 1; background: $primary-darken-3; color: $text-muted; padding: 0 1; text-style: bold;`
- Proxy `.panel-title`: `height: 1; background: $primary-darken-3; color: $text-muted; padding: 0 1;`
- Recon `.recon-panel-label`: `height: 1; text-style: bold; color: $text-muted; border-bottom: solid $primary-darken-2;`
- Intruder `.section-title`: `height: 1; background: $primary-darken-3; color: $text-muted; padding: 0 1;`

Разные реализации одного и того же. Единый класс `.panel-title` сэкономит ~15 строк.

### 4.5 Поля Input с compact

Из 25 Input в проекте 23 используют `compact=True`. Исключения:
- Scanner `opt-input` классы — используют `classes="opt-input"` вместо compact (compact=True присутствует, но переопределяется CSS)
- Settings секция с выпадающим списком (hotkeys) — один Input без compact

Проблема: у Input с `compact=True` высота 1, а у выпадающих/Select-виджетов высота больше. Везде где есть панели с разными высотами (Scanner tab-settings-area с Input + Checkbox) это решается через ручную настройку. Нужен единый `.input-compact` класс для Input и `.widget-compact` для прочих виджетов.

## 5. Миксины и наследование

### 5.1 BaseModuleScreen
- Предоставляет: rename tabs по двойному клику
- Используется: Proxy, Intruder, Scanner, Recon, Repeater, Sequencer
- **Проблема:** абстрактные методы `_start_rename` и `_rename_tab` — каждый экран реализует по-своему или оставляет `pass`

### 5.2 SortableTableMixin
- Предоставляет: `_sort_table()`, `_sort_table_sql()`, `_update_sort_arrows()`
- Используется в классах экранов через MRO: `class ReconScreen(SortableTableMixin, BaseModuleScreen)`
- **Проблема:** миксин зависит от DataTable.HeaderSelected события, которое нужно ловить отдельным хендлером

### 5.3 ToolbarButton
- **Сильная сторона:** variant (success/error/warning/default), disabled, label как свойства
- **Слабая сторона:** нет `pause`/`resume` методов — каждый экран сам переключает label и variant
- **Рекомендация:** добавить статические методы `ToolbarButton.as_start()`, `ToolbarButton.as_pause()`, `ToolbarButton.as_resume()`

## 6. Повторяющиеся паттерны compose

### Паттерн 1: toolbar с кнопками
```python
with Horizontal(id="toolbar"):
    yield ToolbarButton("▶ Start", "btn-start", variant="success")
    yield ToolbarButton("■ Stop",  "btn-stop",  classes="disabled")
```

**Используется:** Intruder, Scanner, Target (частично), Proxy (частично)

**Предложение:** использовать `build_toolbar()` из `toolbar_helper.py` (уже есть, используется в Sequencer). Распространить на все экраны.

### Паттерн 2: TabbedContent внутри экрана
```python
with TabbedContent(id="..."):
    with TabPane("...", id="..."):
        yield ...
```

**Используется:** Intruder, Scanner, Recon, Repeater

### Паттерн 3: DataTable + контекстное меню
```python
table = self.query_one("#table-id", ArrowBackendDataTable)
# populate
# on_data_table_row_selected → _on_data_table_row_selected → контекстное меню
```

**Используется:** Intruder, Recon, Scanner, Proxy

## 7. Размеры и избыточность

| Мера | Значение |
|---|---|
| Всего TCSS строк | 1571 |
| Из них дубликатов | ~300-400 (20-25%) |
| Экран с минимальным TCSS | Extensions (22 строки) |
| Экран с максимальным TCSS | Intruder (273 строки) |
| Scanner (PRO) | 249 строк (из них ~80 — дублируемые паттерны) |
| Кастомные toolbar id | 5 из 12 экранов |

## 8. Рекомендации по рефакторингу

### Фаза 1: Кнопки Start/Stop/Resume (оценка: 4ч)
1. Вынести `_set_running_state()` в BaseModuleScreen как общий метод
2. Переименовать `recon-start`/`recon-stop` → `btn-start`/`btn-stop` в ReconScreen
3. Заменить `on_toolbar_button_pressed` на `@on(ToolbarButton.Pressed, "#btn-start")` в ReconScreen
4. Унифицировать имена флагов: `_running`, `_paused` (сейчас: `_attack_running` в Intruder, `_scanning` в Scanner)

### Фаза 2: CSS-уборка (оценка: 3ч)
1. Создать `.toolbar` класс в toolbar_button.tcss вместо дублирования в 7 TCSS
2. Удалить `.toolbar-sep` из всех TCSS (оставить только в toolbar_button.tcss)
3. Создать `.panel-title` класс для заголовков панелей
4. Пройтись по TCSS, убрать явные `height: 1fr` из DataTable (это default)
5. Удалить неиспользуемые CSS классы (например `.scan-tab-body` в Scanner)

### Фаза 3: compose-шаблоны (оценка: 3ч)
1. Распространить `build_toolbar()` на все экраны (сейчас только Sequencer)
2. Вынести общий паттерн TabbedContent с таблицами в helper или базовый класс
3. Упростить compose: кастомные Horizontal + Vertical заменить на стандартные

### Фаза 4: Аудит импортов и мёртвого кода (оценка: 2ч)
1. Проверить все `from textual_fastdatatable import DataTable` — в некоторых экранах дубль (Recon был)
2. Импорт `pyarrow` — используется только для set_data(), может быть ленивым
3. Поискать неиспользуемые классы CSS

## 9. Итог

Всего ~12 часов на полный рефакторинг. Приоритет — Фаза 1 (кнопки), так как это влияет на UX и стабильность Recon. Фаза 2 (CSS) даст ~25% сокращения кода. Фаза 3 и 4 — код-стайл и чистка.