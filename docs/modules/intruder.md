# Intruder — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/modules/intruder.py` — ядро: `IntruderAttack`, `IntruderConfig`, `IntruderResult`, типы атак
- `pentool/api/intruder_api.py` — публичный API (`IntruderAPI`)
- `pentool/tui/screens/intruder/screen.py` — TUI-экран (`IntruderScreen`)
- `pentool/tui/screens/intruder/screen.tcss` — стили
- `tests/unit/modules/test_intruder.py` — 54 unit-теста

**Горячая клавиша:** `Shift+I`

---

## Назначение

Автоматизированная атака с подстановкой payload'ов в размеченные позиции HTTP-запроса. Поддерживает 4 типа атак, payload-процессинг (URL encode, Base64, HTML encode, MD5), фильтрацию и экспорт результатов. Аналог Burp Suite Intruder.

---

## Типы атак

| Тип | Описание |
|-----|---------|
| **Sniper** | Один набор payload'ов, одна позиция за раз. N позиций × N payload'ов = N² запросов |
| **Battering Ram** | Один набор payload'ов, все позиции одновременно одним значением |
| **Pitchfork** | Несколько наборов, параллельно (zip). N запросов = min длины наборов |
| **Cluster Bomb** | Декартово произведение всех наборов. N = payload₁ × payload₂ × … |

---

## Маркеры позиций

Позиции инъекции обозначаются `§value§`. Например:
```
GET /login?user=§admin§&pass=§password§ HTTP/1.1
Host: example.com
Cookie: session=§abc123§
```

- **`Add §§`** (`btn-add-marker`) — оборачивает выделенный текст в `§...§`
- **`Clear §§`** (`btn-clear-markers`) — удаляет все маркеры
- **`Mark Params`** (`btn-mark-params`) — авто-маркировка query params, form body (urlencoded) и Cookie-заголовка

---

## Компоненты TUI

### Тулбар
| Кнопка | ID | Действие |
|--------|----|----------|
| `▶ Start` | `btn-start` | Запустить атаку |
| `⏸ Pause` | `btn-pause` | Пауза (disabled до старта) |
| `■ Stop` | `btn-stop` | Остановить (disabled до старта) |
| `Clear results` | `btn-clear-results` | Очистить таблицу результатов |
| `Export CSV` | `btn-export-csv` | Экспортировать в CSV |

### Горячие клавиши
| Клавиша | Действие |
|---------|----------|
| `Ctrl+J` | Запустить атаку |
| `Ctrl+P` | Пауза / Возобновить |

### Позиции (`#positions-panel`)
- **`#positions-toolbar`**: Attack type (`btn-attack-type`) + Add §§ / Clear §§ / Mark Params
- **`#attack-type-desc`**: описание выбранного типа атаки
- **`#marker-hint`**: подсказка по маркерам (под attack-type-desc)
- **`#template-editor`** (`TextArea`): HTTP-шаблон запроса с маркерами

### Payload'ы (`#payloads-panel`)
- **`btn-payload-set`**: переключатель активного набора (Set 1 / Set 2 / ...)
- **Кнопки** (`#payload-buttons`, `ToolbarButton`, `height: 1`):
  - `Add` (`btn-payload-add`)
  - `Remove` (`btn-payload-remove`)
  - `Clear` (`btn-payload-clear`)
  - `Load from file…` (`btn-payload-load`)
  - `Generate…` (`btn-payload-generate`)
  - `🧠 Smart…` (`btn-payload-smart`, PRO)
- **`#payload-list`** (`ListView`): текущие payload'ы активного набора
- **Processing** (`#processing-bar`): URL encode / Base64 / HTML encode / MD5

### Результаты (`#results-area`)
- `ProgressBar` (`#attack-progress`) — прогресс атаки
- `DataTable` (`#results-table`) — `#` | `Payload` | `Status` | `Length` | `Time (ms)` | `Error`
- Фильтры по Status, Length (>N, <N); сортировка по колонкам

---

## Payload-процессинг

Порядок применения при отправке каждого payload'а:
1. URL encode (если включён)
2. Base64 encode
3. HTML encode
4. MD5 hash

---

## Датаклассы

```python
@dataclass
class IntruderConfig:
    template: str                    # HTTP-шаблон с §маркерами§
    payloads: list[list[str]]        # наборы payload'ов [[set1], [set2], ...]
    attack_type: AttackType          # SNIPER | BATTERING_RAM | PITCHFORK | CLUSTER_BOMB
    target_host: str
    target_port: int = 80
    use_https: bool = False
    url_encode: bool = False
    base64_encode: bool = False
    html_encode: bool = False
    md5_hash: bool = False
    request_delay: float = 0.0
    concurrency: int = 1

@dataclass
class IntruderResult:
    id: str
    attack_id: str
    request_number: int
    payload_values: list[str]        # значения подставленных payload'ов
    request_raw: str                 # итоговый HTTP-запрос
    response_status: Optional[int]
    response_length: Optional[int]
    response_time_ms: Optional[float]
    error: Optional[str]
    timestamp: datetime
```

---

## Публичный API

### `IntruderAPI`

```python
from pentool.api.intruder_api import (
    IntruderAPI, AttackType, IntruderConfig, IntruderResult,
    count_markers, process_payload,
    generate_numeric_payloads, generate_char_payloads,
)

api = IntruderAPI(db_path="pentool.db")

# Запустить атаку
config = IntruderConfig(
    template="GET /?id=§1§ HTTP/1.1\r\nHost: example.com\r\n\r\n",
    payloads=[["1", "2", "3", "' OR 1=1--"]],
    attack_type=AttackType.SNIPER,
    target_host="example.com",
    target_port=80,
    use_https=False,
)
attack_id = await api.start_attack(
    config,
    on_result=lambda r: print(r.response_status, r.payload_values),
    on_progress=lambda done, total: print(f"{done}/{total}"),
)

# Управление
await api.pause()
await api.resume()
await api.stop()

# Результаты
results: list[IntruderResult] = api.get_results()
done, total = api.get_progress()
api.is_running  # property: bool

# Payload'ы
payloads = await api.load_payloads("/path/to/wordlist.txt")
nums = await api.generate_numeric(start=1, end=100, step=1)
chars = await api.generate_chars(charset="abcdef0123456789", min_len=8, max_len=8)

# Экспорт
api.export_csv("/tmp/results.csv")

# Проект
data = api.export_project_data()    # → {"results": [...]}
count = api.import_project_data(data)
```

### Вспомогательные функции

```python
# Подсчёт маркеров в шаблоне
n = count_markers("GET /?a=§1§&b=§2§ HTTP/1.1")  # → 2

# Применение процессинга к payload'у
result = process_payload(
    "test",
    url_encode=True, base64_encode=False, html_encode=False, md5_hash=False
)  # → "test" (без спецсимволов)

# Генерация числовых payload'ов
nums = generate_numeric_payloads(1, 100, step=1)   # ["1", "2", ..., "100"]

# Генерация символьных payload'ов
chars = generate_char_payloads("abc", min_len=2, max_len=2)  # ["aa", "ab", ...]
```

---

## Известные проблемы / Исправленные баги

- `PayloadDropZone` удалена из compose и импортов (была источником ошибки монтирования).
- Кнопки payload (Add/Remove/Clear/Load/Generate) — `ToolbarButton` с `height: 1` в `#payload-buttons`.
- `_load_file_async`: индекс активного набора `idx` захватывается до открытия диалога — иначе может измениться пока диалог открыт.
- `_InputDialog`: кнопка X закрытия + кнопка «Add» (не «OK»), `height: 12`.
- `_GenerateDialog`: кнопка X закрытия, `height: 16`.
- Scope/MR диалоги: `ToolbarButton` для Save/Cancel (не стандартный `Button`).

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Intruder (Shift+I) — экран отображается корректно
- [ ] В `#template-editor` вставить:
  ```
  GET /?id=§1§ HTTP/1.1
  Host: example.com
  
  ```
- [ ] Добавить payload'ы: `1`, `2`, `3`, `' OR 1=1--`
- [ ] Нажать `▶ Start` → атака запускается, ProgressBar движется
- [ ] Результаты появляются в таблице: Status | Length | Time | Payload
- [ ] `⏸ Pause` → атака останавливается, кнопка меняет состояние
- [ ] `⏸ Resume` (Ctrl+P) → атака продолжается
- [ ] `■ Stop` → атака завершается
- [ ] `Export CSV` → файл сохраняется с колонками #, Payload, Status, Length, Time, Error

### Позиции и маркеры
- [ ] Выделить текст `1` в шаблоне, нажать `Add §§` → текст становится `§1§`
- [ ] `Clear §§` → маркеры удалены, текст `1` возвращается
- [ ] `Mark Params`: шаблон `GET /?user=admin&pass=test HTTP/1.1\nHost: x\n\n` → оба параметра маркированы: `§admin§` и `§test§`
- [ ] Переключить Attack type → описание меняется под тулбаром

### Типы атак (с реальным HTTP)
- [ ] **Sniper**: 2 маркера, 3 payload'а → 6 запросов (каждая позиция по очереди)
- [ ] **Battering Ram**: 2 маркера, 3 payload'а → 3 запроса (одновременно оба)
- [ ] **Pitchfork**: 2 набора по 3 payload'а → 3 запроса (попарно)
- [ ] **Cluster Bomb**: 2 набора по 2 payload'а → 4 запроса (2×2)

### Payload'ы
- [ ] `Add` → диалог → ввести `test` → появляется в ListView
- [ ] `Remove` → удаляет выбранный элемент
- [ ] `Clear` → список пустой
- [ ] `Load from file…` → диалог → загрузить wordlist.txt → список заполнен
- [ ] `Generate…` → диалог → числа `from=1 to=10 step=1` → 10 элементов в списке
- [ ] URL encode: payload `<script>` → отправляется как `%3Cscript%3E`
- [ ] Base64: payload `test` → отправляется как `dGVzdA==`

### DEMO (дополнительно)
- [ ] Фильтр по Status ≠ 200 → только аномальные ответы
- [ ] Сортировка по Length ▼ → самые длинные ответы сверху
- [ ] Загрузить запрос из Proxy → шаблон автоматически заполнен
- [ ] `🧠 Smart…` без PRO → уведомление о необходимости лицензии
- [ ] Сохранить проект → результаты атаки восстанавливаются при открытии
