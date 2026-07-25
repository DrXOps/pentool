# Спецификация: RepeaterScreen (TUI)

> Файл: `pentool/tui/screens/repeater/screen.py`
> Слой: `tui/`
> Зависит от: `api/repeater_api.py`
> Последнее обновление: 2026-03-25

---

## 1. Назначение

`RepeaterScreen` — экран ручной отправки HTTP-запросов. Поддерживает несколько вкладок (как Burp Repeater), редактирование запроса, отправку, отображение ответа и историю отправок.

---

## 2. Зависимости

```
tui/screens/repeater/screen.py
  ← api/repeater_api.py        (RepeaterAPI, RepeaterEntry)
  ← tui/widgets/request_editor.py  (RequestEditor)
  ← tui/widgets/resize_handle.py   (ResizeHandle)
```

**НЕ импортирует из:** `modules/`.

---

## 3. Макет

```
┌─────────────────────────────────────────────────────────────────┐
│ [Send ▶] [New Tab +] [Clear] [< Prev] [> Next] [Copy as curl]  │  ← Toolbar (верх!)
├────────────┬────────────────────────────────────────────────────┤
│ Request    │ Response                                           │
│            │                                                    │
│ GET / HTTP │ HTTP/1.1 200 OK                                   │
│ Host: ...  │ Content-Type: text/html                           │
│            │ <html>...</html>                                  │
│            │                                                    │
├────────────┴────────────────────────────────────────────────────┤
│    ResizeHandle (горизонтальный, между req/resp и логом)        │
├─────────────────────────────────────────────────────────────────┤
│  [лог запросов / статус]                                        │  ← RichLog
└─────────────────────────────────────────────────────────────────┘
```

**Вкладки Repeater** (TabbedContent в верхней части):
- Каждая вкладка — отдельная пара Request/Response
- Добавление: кнопка `[New Tab +]` или `Ctrl+T`
- Удаление: кнопка `[×]` на вкладке

---

## 4. Виджеты и ID

| ID | Виджет | Описание |
|----|--------|----------|
| `#toolbar` | `Horizontal` | Тулбар с кнопками (наверху!) |
| `#btn-send` | `Button` | Отправить запрос |
| `#btn-new-tab` | `Button` | Новая вкладка |
| `#btn-clear` | `Button` | Очистить запрос |
| `#repeater-tabs` | `TabbedContent` | Контейнер вкладок |
| `#request-editor` | `RequestEditor` (TextArea) | Редактор запроса |
| `#response-viewer` | `TextArea` (readonly) | Просмотр ответа |
| `#resize-req-resp` | `ResizeHandle` | Между req и resp панелями |
| `#resize-content-log` | `ResizeHandle` | Между контентом и логом |
| `#log` | `RichLog` | Лог отправок |

**Правило:** все кнопки тулбара всегда в DOM.

---

## 5. Ключевые методы

```python
def compose(self) -> ComposeResult
async def on_mount(self) -> None

@work
async def _do_send(self) -> None          # отправить текущий запрос
def action_send(self) -> None             # Ctrl+Space → _do_send
def action_new_tab(self) -> None          # Ctrl+T
def action_close_tab(self) -> None

def _get_current_request(self) -> Optional[ParsedRequest]  # распарсить из редактора
def _show_response(self, response: ParsedResponse) -> None  # обновить viewer

def load_request(self, request: ParsedRequest) -> None     # из ProxyScreen (Send to Repeater)
```

---

## 6. События

| Событие | Источник | Обработчик | Действие |
|---------|---------|------------|---------|
| `Button.Pressed` `#btn-send` | тулбар | `action_send` | `_do_send()` |
| `Key("ctrl+space")` | глобально | `action_send` | `_do_send()` |
| `Button.Pressed` `#btn-new-tab` | тулбар | `action_new_tab` | добавить вкладку |
| `TabbedContent.TabActivated` | `#repeater-tabs` | `on_tab_activated` | переключить req/resp |

---

## 7. Хоткеи (Repeater-специфичные)

| Хоткей | Действие |
|--------|---------|
| `Ctrl+Space` | Send |
| `Ctrl+T` | New Tab |
| `Ctrl+W` | Close Tab |
| `Ctrl+D` | Diff с предыдущим ответом (планируется) |

---

## 8. Интеграция с ProxyScreen

При выборе в ProxyScreen "Send to Repeater":
1. `app.get_screen("repeater")` → `RepeaterScreen`
2. `repeater_screen.load_request(intercepted_req.to_parsed())` — загрузить в новую вкладку
3. Переключить активный модуль на Repeater

---

## 9. Тест-кейсы

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | Монтирование | нет ошибок, `#btn-send` в DOM |
| 2 | `load_request(req)` | текст запроса в `#request-editor` |
| 3 | `action_send()` → mock HTTP | ответ в `#response-viewer` |
| 4 | Ошибка сети → notify | уведомление severity="error" |
| 5 | `action_new_tab()` | новая вкладка добавлена |
| 6 | `action_close_tab()` | вкладка удалена, предыдущая активна |
| 7 | Лог обновлён после отправки | `#log` содержит статус ответа |

---

## 10. Известные проблемы

- Кнопки Send, New Tab были внизу — перенесены наверх (тулбар).
- Лог слишком мал — добавить `ResizeHandle` между контентом и логом.
- Переименование вкладки двойным кликом — не реализовано.
