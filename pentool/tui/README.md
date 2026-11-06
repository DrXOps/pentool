# pentool/tui — устройство слоя

TUI-слой: 21 430 строк Python в 95 файлах и 2 670 строк `.tcss` в 44
файлах. Каталог собирает всё, что нужно знать до первой правки: где точка
сборки, как ходят сообщения, как не сделать хендлер, который никогда не
вызовется.

Полные документы аудита 2026-11-06: [`docs/tui-audit/`](../../docs/tui-audit/) —
[REPORT](../../docs/tui-audit/REPORT.md) (находки),
[DECISIONS](../../docs/tui-audit/DECISIONS.md) (ADR),
[CONVENTIONS](../../docs/tui-audit/CONVENTIONS.md) (правила),
[COMPONENTS](../../docs/tui-audit/COMPONENTS.md) (каталог),
[SUMMARY](../../docs/tui-audit/SUMMARY.md) (итоги).

---

## 1. Структура

```
pentool/tui/
  app.py             PentoolApp — единственная точка сборки (composition root)
  screen_registry.py SCREEN_MAP + lazy-импорт PRO-экранов
  messages.py        сообщения между экранами (вверх в App)
  constants.py       только SCREEN_* (остальное — на месте, ADR-9)
  screens/           экраны-«модули»: proxy, intruder, target, repeater,
                     dashboard, settings, decoder, comparer, sequencer,
                     extensions, scanner_unavailable
  widgets/           переиспользуемые виджеты (таблицы, тулбары, панели)
  dialogs/           модальные окна (BaseDialog — база)
  mixins/            поведение без собственного DOM
  hotkeys/           реестр горячих клавиш и BINDINGS по умолчанию
  *.tcss             стили рядом с виджетами, которые их используют
```

## 2. Как экран попадает на экран

Экраны — это `Widget`, а не `Screen`. `PentoolApp.compose()` монтирует все
доступные экраны один раз в `ContentSwitcher`; переключение — через
`ContentSwitcher.current`. Следствия:

- `on_show` / `on_hide` доходят до экранов (проверено `run_test()`);
- все экраны существуют одновременно → **общие `id` недопустимы**:
  `query_one("#toolbar")` вернёт первый по порядку обхода, а не тот, что
  на экране. Поэтому `Toolbar` не задаёт `id` по умолчанию;
- экран не должен рассчитывать на `on_mount` при каждом показе — он
  вызывается один раз.

## 3. Сообщения

Три направления, три механизма:

| Направление | Механизм | Пример |
|---|---|---|
| Виджет → владелец | вложенный `Message` на виджете | `ContentPanel.CopyRequested` |
| Экран → экран | через `PentoolApp`, классы из `messages.py` | `SendToRepeater` |
| Домен → TUI | `EventBus` + `ProxyEventHandlersMixin` | `ProxyRequestCaptured` |

### 3.1 Главное правило: имя хендлера — из класса сообщения

```python
ContentPanel.PasteRequested.handler_name
# 'on_content_panel_paste_requested'   ← ровно так и надо называть метод
```

Textual резолвит такие методы **по MRO**, поэтому они работают и в
миксинах. `@on(...)` резолвится только в классе, объявившем декоратор:
в обычном миксине он **не регистрируется** и молча не вызывается. Двойное
подчёркивание нужно только для классов с ведущим `_`.

Проверка: `tests/unit/tui/test_handler_name_dispatch.py` обходит AST всех
классов в `pentool/tui` и падает, если `on_*` не соответствует ни одному
реальному `handler_name`.

### 3.2 Виджет не лезет к экрану

Наверх — только `post_message`. `hasattr`-обход предков находит «любой
экран с таким методом», включая тот, что сейчас в другом табе.

## 4. Воркеры

- `WorkerManager` умеет: `add_worker`, `cancel_all`, `cancel_group`,
  `cancel_node`, `start_all`, `wait_for_complete`. Метода `cancel(name)`
  нет.
- Воркеры запускаются с `group=`; отмена — `cancel_group(self, group)`.
  Готовый образец: `AutoSaveMixin._start_save_worker` →
  `AutoSaveMixin.SAVE_WORKER_GROUP`.
- БД, сеть и файлы — только в воркерах; в теле хендлера — только
  постановка задачи.

## 5. Подписки

| Источник | Подписка | Отписка |
|---|---|---|
| `EventBus` (виджет) | `on_mount` / `_init_…` | `on_unmount` |
| `EventBus` (App) | `PentoolApp.on_mount` | `_on_exit_app` |
| `Config.add_observer` | `PentoolApp.on_mount` | `_on_exit_app` |

Хендлер хранится в атрибуте, иначе отписка невозможна. Образец —
`mixins/ai_sync.py::AiModeSyncMixin`.

## 6. Слои

`utils ← core ← modules ← api ← services ← tui`. Проверяется
`tools/check_layers.py`.

- `tui → modules` и `tui → storage` — запрещены.
- Composition root — только `PentoolApp`.
- Путь к БД — `app.db_path` (публичный), не `app._db_path`.

## 7. Стили

CSS — в `.tcss` рядом с виджетом, подключается через
`DEFAULT_CSS = (Path(__file__).parent / "x.tcss").read_text(...)`. Цвета —
только токены `$text`, `$surface`, `$primary`, `$success`, `$warning`,
`$error`, `$accent`, `$background` и производные; hex и `rgb()` — нет
(сейчас их 0).

Классы-состояния — по конвенции Textual: `-active`, `-disabled`, `-on`,
`-dragging`. Варианты кнопок — `variant-success`, `variant-warning`.

## 8. Тесты

```bash
scripts/run-tests.sh                    # гейт: tests/unit, ставит .claude/state/tests-passed
uv run pytest tests/unit/tui -q         # только TUI
uv run python tools/check_layers.py
uv run ruff check --select F pentool/tui
```

Правило: тест проверяет **эффект** (что оказалось в буфере, что в
`TextArea`, что воркер не доехал до конца), а не «не бросил исключение».
`app.run_test()` + `pilot`; `await pilot.pause()` после каждого действия.

## 9. Что делать перед первой правкой

1. Прочитать [`CONVENTIONS.md`](../../docs/tui-audit/CONVENTIONS.md) §1 — про
   хендлеры. Это самая частая ошибка в этом слое.
2. Найти существующий компонент в
   [`COMPONENTS.md`](../../docs/tui-audit/COMPONENTS.md) §7 — «задача →
   компонент».
3. Проверить `MYPLANS/tech_debt.md`: часть пунктов из SUMMARY §5 уже
   расписана там.
