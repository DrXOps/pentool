# Comparer — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/modules/comparer.py` — ядро: алгоритм diff, датаклассы (`DiffLine`, `CompareStats`, `DiffResult`)
- `pentool/tui/screens/comparer/screen.py` — TUI-экран (`ComparerScreen`)
- `pentool/tui/screens/comparer/screen.tcss` — стили
- `tests/unit/modules/test_comparer.py` — 30 unit-тестов

**Горячая клавиша:** `Shift+C`

---

## Назначение

Модуль сравнивает два произвольных текста (HTTP-ответы, тела запросов, токены, конфиги) построчно с подсветкой различий. Аналог Burp Suite Comparer.

---

## Алгоритм сравнения

Используется `difflib.SequenceMatcher(None, left_lines, right_lines, autojunk=False)`. Каждая строка diff получает тег:

| Тег | Значение | Маркер | Цвет в UI |
|-----|----------|--------|-----------|
| `equal` | Строки идентичны | ` ` | серый (dim) |
| `insert` | Строка добавлена справа | `+` | зелёный |
| `delete` | Строка удалена слева | `-` | красный |
| `replace` | Строка изменена | `-` / `+` | красный + зелёный |

Метрика схожести: `SequenceMatcher.ratio()` → `CompareStats.similarity` (0.0–1.0).

Ограничения вывода: максимум 2000 строк в RichLog, строки обрезаются до 120 символов.

---

## Компоненты TUI

### Тулбар (`#cmp-toolbar`)
| Кнопка | ID | Действие |
|--------|----|----------|
| `⇄ Compare` | `btn-cmp-compare` | Запустить сравнение |
| `↑ Load Left` | `btn-cmp-load-left` | Загрузить левую панель из файла |
| `↑ Load Right` | `btn-cmp-load-right` | Загрузить правую панель из файла |
| `📋 Copy Diff` | `btn-cmp-copy` | Скопировать diff в буфер (plain text) |
| `🗑 Clear` | `btn-cmp-clear` | Очистить всё |

### Горячие клавиши
| Клавиша | Действие |
|---------|----------|
| `Ctrl+Enter` | Сравнить |
| `Ctrl+L` | Очистить |

### Зоны
- **`#cmp-edit-area`** — две панели `TextArea` (`#cmp-left` и `#cmp-right`) для ввода текста; заголовки меняются при загрузке файла на имя файла
- **`#cmp-stat-bar`** — статус-строка: `+N added / -N removed / ~N changed / =N equal / Similarity: N%`
- **`#cmp-diff-area`** — `RichLog` с diff-выводом (max 2000 строк, строки обрезаются до 120 символов)

---

## Датаклассы модуля

```python
@dataclass
class DiffLine:
    tag: str        # "equal" | "replace" | "insert" | "delete"
    left: str       # текст левой стороны
    right: str      # текст правой стороны
    line_left: int  # номер строки слева (0 если нет)
    line_right: int # номер строки справа (0 если нет)

@dataclass
class CompareStats:
    total_left: int
    total_right: int
    equal_lines: int
    added_lines: int
    removed_lines: int
    changed_lines: int
    similarity: float   # 0.0–1.0

    @property
    def similarity_pct(self) -> int:  # int(similarity * 100)

@dataclass
class DiffResult:
    lines: list[DiffLine]
    stats: CompareStats

    def rich_text(self) -> str: ...  # Rich markup для вывода в RichLog
```

---

## Публичный API

### Модуль `pentool.modules.comparer`

```python
from pentool.modules.comparer import compare, compare_lines, compare_bytes

# Сравнить два текста построчно
result: DiffResult = compare("text A\nline2", "text B\nline2")

# Сравнить два списка строк напрямую
result = compare_lines(["line1", "line2"], ["line1", "changed"])

# Сравнить байтовые потоки (декодируются как UTF-8 с заменой)
result = compare_bytes(b"bytes A", b"bytes B")

# Статистика
print(result.stats.similarity_pct)  # 0–100
print(result.stats.added_lines)     # кол-во добавленных строк
print(result.stats.removed_lines)   # кол-во удалённых строк
print(result.stats.changed_lines)   # кол-во изменённых строк
print(result.stats.equal_lines)     # кол-во одинаковых строк

# Обход строк diff
for line in result.lines:
    print(line.tag, line.left, line.right)

# Rich-разметка для вывода в RichLog
markup = result.rich_text()
```

### Публичный API экрана `ComparerScreen`

```python
# Загрузить текст программно (из Proxy/Repeater)
screen.load_left(text: str, label: str = "Left") -> None
screen.load_right(text: str, label: str = "Right") -> None

# Выполнить сравнение
screen.action_compare() -> None

# Очистить всё (оба TextArea, diff-лог, заголовки)
screen.action_clear() -> None
```

### Интеграция из других модулей

```python
# Из Proxy или Repeater напрямую вызвать:
comparer = self.app.query_one(SCREEN_COMPARER, ComparerScreen)
comparer.load_left(response_body, label="Response A")
comparer.load_right(response_body, label="Response B")
comparer.action_compare()
```

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Comparer (Shift+C) — экран отображается корректно
- [ ] Ввести разные тексты в Left и Right, нажать `⇄ Compare` — diff отображается в нижней панели
- [ ] Нажать `Ctrl+Enter` — то же что кнопка Compare
- [ ] Статус-строка показывает: `+N added / -N removed / ~N changed / =N equal / Similarity: N%`
- [ ] Идентичные тексты — `Similarity: 100%`, все строки серые (`=`)
- [ ] Полностью разные тексты — `Similarity: 0%`, все строки красные/зелёные
- [ ] Нажать `↑ Load Left` → диалог выбора файла → файл загружается в левую панель, заголовок меняется на имя файла
- [ ] Нажать `↑ Load Right` → аналогично для правой панели
- [ ] После сравнения нажать `📋 Copy Diff` — в буфере plain text без Rich-разметки
- [ ] `🗑 Clear` — очищает оба TextArea, diff-лог и заголовки ("Left" / "Right")
- [ ] `Ctrl+L` — то же что Clear
- [ ] Тест с длинными строками (>120 символов) — обрезаются в diff-логе, нет ошибок

### DEMO (дополнительно)
- [ ] Загрузить файл с не-UTF-8 содержимым — нет ошибки, символы заменяются (UTF-8 with errors='replace')
- [ ] Сравнить два HTTP-ответа (скопировать из Proxy) — различия в заголовках подсвечены корректно
- [ ] Load Left из одного файла + Load Right из другого — заголовки показывают имена файлов
- [ ] Большой файл (>1000 строк) — diff отображается без зависания (max_lines=2000)
- [ ] Вызов `load_left()` / `load_right()` из другого модуля — текст появляется в нужной панели
