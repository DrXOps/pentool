# Спецификация: IntruderScreen (TUI)

> Файл: `pentool/tui/screens/intruder/screen.py`
> Слой: `tui/`
> Зависит от: `api/intruder_api.py`
> Последнее обновление: 2026-03-25

---

## 1. Назначение

`IntruderScreen` — экран автоматизированных атак (fuzzing). Позволяет настроить шаблон запроса с позициями (маркерами `§...§`), выбрать payload-листы, запустить атаку и просмотреть результаты.

---

## 2. Зависимости

```
tui/screens/intruder/screen.py
  ← api/intruder_api.py       (IntruderAPI, IntruderConfig, IntruderResult, AttackType)
  ← tui/dialogs/file_selector.py  (FileSelectorDialog)
  ← tui/widgets/request_editor.py
  ← tui/widgets/resize_handle.py
```

---

## 3. Макет

```
┌─────────────────────────────────────────────────────────────────┐
│ [▶ Start] [⏸ Pause] [⏹ Stop] Attack: Sniper ▼  Threads: 10    │  ← Toolbar
├──────────────────────────┬──────────────────────────────────────┤
│ POSITIONS                │ PAYLOADS                             │
│                          │                                      │
│ POST /login HTTP/1.1     │ Payload Set 1: [список]             │
│ Host: example.com        │ [📂 Load from file]                 │
│ ...                      │ [+ Add] [- Remove]                  │
│ username=§admin§         │                                      │
│ password=§password§      │ ○ Simple list                       │
│                          │ ○ Numbers (from/to/step)            │
│ [Add §] [Clear §]        │ ○ Charset brute force               │
├──────────────────────────┴──────────────────────────────────────┤
│    ResizeHandle                                                  │
├─────────────────────────────────────────────────────────────────┤
│ RESULTS  [Export CSV]                                           │
│ # │ Payload │ Status │ Length │ Time ms │ Error                 │
│ 1 │ admin   │ 302    │  0     │  234    │                      │
│ 2 │ test    │ 401    │  45    │  120    │                      │
└─────────────────────────────────────────────────────────────────┘
```

**Без вложенных вкладок** — Positions + Payloads рядом (2 колонки), Results снизу.

---

## 4. Виджеты и ID

| ID | Виджет | Описание |
|----|--------|----------|
| `#toolbar` | `Horizontal` | Тулбар |
| `#btn-start` | `Button` | Запустить атаку |
| `#btn-pause` | `Button` | Пауза |
| `#btn-stop` | `Button` | Остановить |
| `#select-attack-type` | `Select` | Тип атаки (Sniper/Pitchfork/...) |
| `#positions-editor` | `RequestEditor` | Редактор шаблона с маркерами §§ |
| `#btn-add-marker` | `Button` | Добавить §§ вокруг выделенного |
| `#btn-clear-markers` | `Button` | Убрать все §§ |
| `#payloads-panel` | `VerticalScroll` | Панель настройки payload'ов |
| `#payload-list` | `ListView` | Список payload'ов |
| `#btn-load-file` | `Button` | Загрузить из файла |
| `#results-table` | `DataTable` | Таблица результатов |
| `#btn-export` | `Button` | Экспорт в CSV |
| `#resize-positions-results` | `ResizeHandle` | Между позициями/payload и результатами |
| `#progress-bar` | `ProgressBar` | Прогресс атаки |

---

## 5. Ключевые методы

```python
def compose(self) -> ComposeResult
async def on_mount(self) -> None

async def action_start(self) -> None     # запустить IntruderAPI.start_attack()
async def action_pause(self) -> None     # IntruderAPI.pause()
async def action_stop(self) -> None      # IntruderAPI.stop()

def _on_result(self, result: IntruderResult) -> None  # callback → добавить строку в таблицу
def _on_progress(self, done: int, total: int) -> None  # callback → обновить ProgressBar

def _build_config(self) -> IntruderConfig    # собрать конфиг из UI
def load_request(self, request: ParsedRequest) -> None  # из ProxyScreen

async def _load_payloads_from_file(self) -> None   # FileSelectorDialog
def _add_marker(self) -> None                       # §§ вокруг выделения
def _clear_markers(self) -> None
```

---

## 6. Типы атак (AttackType)

| Тип | Описание | Payload-листов |
|-----|---------|----------------|
| `SNIPER` | 1 маркер, все payloads поочерёдно | 1 |
| `BATTERING_RAM` | N маркеров, один payload для всех | 1 |
| `PITCHFORK` | N маркеров, N payload-листов попарно | N |
| `CLUSTER_BOMB` | N маркеров, декартово произведение | N |

---

## 7. Колонки таблицы результатов

```python
_RESULT_COLS = ["#", "Payload", "Status", "Length", "Time ms", "Error"]
```

Сортировка по любой колонке (клик по заголовку).
Цветовая индикация по статусу (2xx зелёный, 3xx жёлтый, 4xx оранжевый, 5xx красный) — планируется.

---

## 8. Тест-кейсы

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | Монтирование | нет ошибок, все ID в DOM |
| 2 | `load_request(req)` | текст в `#positions-editor` |
| 3 | `_add_marker()` при выделенном тексте | `§выделенный§` |
| 4 | `_build_config()` → `IntruderConfig` | правильный шаблон, payloads |
| 5 | `action_start()` → mock атака | результаты в `#results-table` |
| 6 | `action_pause()` / `action_stop()` | атака остановлена |
| 7 | Загрузка файла payload | `#payload-list` обновлён |
| 8 | `action_start()` без маркеров | уведомление об ошибке |
| 9 | Прогресс → ProgressBar | `value` соответствует done/total |
| 10 | Export CSV | файл создан с результатами |

---

## 9. Интеграция с ProxyScreen

"Send to Intruder" из контекстного меню:
1. Запрос передаётся в `IntruderScreen.load_request(req)`
2. Переключение на вкладку Intruder
3. Пользователь вручную добавляет маркеры §§
