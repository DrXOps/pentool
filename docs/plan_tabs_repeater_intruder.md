# План: Табы в Repeater и Intruder

## Цель
Внедрить единую систему табов (`BaseModuleScreen`) в Repeater и Intruder.
Табы должны быть изолированными: каждый таб хранит своё состояние.
После внедрения оба модуля работают как Scanner — с переименованием, сохранением в БД, независимыми табами.

---

## 1. Repeater — есть табы, нет BaseModuleScreen

Repeater уже имеет табы (TabbedContent), `_tabs` список, `_RepeaterTabState`, 
но не наследует `BaseModuleScreen` и не использует переименование двойным кликом.

### Изменения:

**1.1 Класс**
- Добавить `BaseModuleScreen` в предки
- Убрать ручной `on_click` если он есть (BaseModuleScreen даёт свой)
- Задать конфиг:
  ```python
  _rename_input_id = "repeater-rename-input"
  _rename_tab_prefix = "repeater-tab-"
  _rename_tabs_widget_id = "repeater-tabs"
  ```

**1.2 `_RepeaterTabState` — дополнить**
- `tab_id`, `name`, `request_text`, `response_text`, `headers_text` — уже есть
- Добавить `tab_uid: str` (для БД) — как в Scanner `_ScanTabState`

**1.3 compose()**
- Переименовать TabbedContent id в `"repeater-tabs"` (если другое)
- Input для переименования добавить в compose или mount

**1.4 `_start_rename` / `_rename_tab`**
- Реализовать — показать Input, обновить tab.name + TabPane title

**1.5 on_tabbed_content_tab_focused**
- Переключение `_active_tab_id` — уже есть

**1.6 Сохранение в БД**
- `_auto_save_tab(state)` — сохранить request/response
- `_load_tabs_from_db()` — загрузить список табов при монтировании
- `_save_tab_state(state)` — перенести из текущих `_do_auto_save`

---

## 2. Intruder — нет табов, нужна архитектура

Intruder сейчас моно-экран. Нужно создать систему табов с нуля.

### 2.1 Класс `_IntruderTabState`

```python
@dataclass
class _IntruderTabState:
    tab_id: str
    tab_uid: str = ""        # UUID для БД
    name: str = "New Tab"
    # Target
    target_url: str = ""
    # Template
    template_text: str = ""
    # Attack config
    attack_type: AttackType = AttackType.SNIPER
    thread_count: int = 1
    delay_ms: int = 0
    # Payloads
    payload_sources: list = field(default_factory=list)
    # Results
    all_results: list = field(default_factory=list)
    result_count: int = 0
    # Runtime state
    scanning: bool = False
    paused: bool = False
    stop_requested: bool = False
    # Настройки для Resume
    last_payload_sets: list | None = None
```

### 2.2 compse() — разбить на табы

**Внутри таба (индивидуально):**
- `HttpView` / TextArea шаблона
- Input target URL
- Select attack type
- PayloadSource список
- DataTable результатов
- ProgressBar
- Status label
- Detail panel

**Глобальный (один на экран):**
- Toolbar (Start/Stop, очистка, экспорт)
- Filter bar (IntruderFilterBar)
- Остальное

```python
def compose(self) -> ComposeResult:
    yield Toolbar(...)  # глобальный
    with TabbedContent(id="intruder-tabs"):
        # табы создаются динамически
        yield TabPane("New Tab", id="intruder-tab-new")
    with Vertical(id="intruder-bottom"):
        yield IntruderFilterBar(...)
```

### 2.3 `action_new_tab`
- Создать `_IntruderTabState`
- Mount содержимое таба (HttpView, Input, PayloadSource, DataTable)
- `_active_tab_id = tab_id`

### 2.4 `action_close_tab`
- Удалить из `_tabs`
- Удалить TabPane
- Закрыть воркер если running
- Переключиться на соседний таб

### 2.5 `_active_tab property`
- Прокси на active `_IntruderTabState` (как в Scanner)

### 2.6 Сохранение / загрузка
- При монтировании: `_load_tabs_from_db()`
- При старте атаки: `_auto_save_tab(state)`
- При закрытии: `_auto_save_tab(state)`
- При смене таба: автосохранение

### 2.7 on_switch
- Перепривязать _ssw, фильтры, таблицу к активному табу

---

## 3. Таблица результатов — в таб

Таблица IntruderResultsTable сейчас одна на весь экран:

```python
yield IntruderResultsTable(id="intruder-results-table")
```

Нужно:
- Создавать DataTable внутри таба (в `action_new_tab`, mount)
- ID: `"intruder-results-{tab_id}"`
- `_fill_results()` — работать с таблицей активного таба
- `_clear_results()` — только для активного таба

---

## 4. Пэйлоады — в таб

PayloadSource список сейчас:

```python
self._payloads: list[PayloadSource] = []
```

Нужно переместить в `_IntruderTabState.payload_sources`.

- `_load_into_payload_list()` — загрузить пэйлоады активного таба
- `_update_payload_select()` — по active табу
- Payload editor виджет — `mount` внутри таба, id: `"payload-editor-{tab_id}"`

---

## 5. Что остаётся глобальным

- Toolbar (StartStopWidget)
- IntruderFilterBar
- HintBar (уже глобальный)
- Контекстное меню

---

## 6. Аудит — что сломается

- `action_start()` — должен читать target_url/template/etc из active таба
- `action_stop()` — стопать воркер active таба
- `_run_attack()` — брать всё из active таба
- `on_worker_state_changed` — проверять active таб
- `on_data_table_row_selected` — читать из `_active_tab.all_results`
- SendToRepeater — читать из active таба

Все методы сейчас работают с `self._*`. Нужно заменить на `self._active_tab.*`.

---

## Порядок реализации

1. Repeater — быстро (уже есть табы, только BaseModuleScreen + rename)
2. Intruder TabState — создать класс, перенести поля
3. Intruder compose — разбить на табы
4. Intruder action_* — переключить на `_active_tab.*`
5. Intruder payloads — перенести в таб
6. Intruder results — перенести в таб
7. Intruder сохранение в БД