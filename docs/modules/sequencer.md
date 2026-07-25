# Sequencer — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/modules/sequencer.py` — ядро: анализ энтропии, датаклассы
- `pentool/tui/screens/sequencer/screen.py` — TUI-экран
- `pentool/tui/screens/sequencer/screen.tcss` — стили
- `tests/unit/modules/test_sequencer.py` — 34 unit-теста

**Горячая клавиша:** `Shift+Q`

---

## Назначение

Анализ случайности и стойкости токенов: session ID, CSRF-токенов, JWT, nonce и т.д. Определяет алфавит, энтропию и выносит вердикт (WEAK / MODERATE / GOOD / STRONG). Аналог Burp Suite Sequencer.

---

## Алгоритм анализа

1. **Определение алфавита** (`charset_size`): hex-строки → 16, lower/upper/digits/spec считаются суммарно
2. **Энтропия на символ** (`token_entropy`): формула Шеннона — `H = -Σ p·log₂(p)`
3. **Суммарная энтропия** (`total_entropy_bits`): `H × len(token)`
4. **Реальная стойкость** (`effective_bits`): `min(mean_bits, theoretical_bits)`

### Пороги оценки
| Effective bits | Вердикт |
|---------------|---------|
| < 32 | `WEAK ⚠️` |
| 32–63 | `MODERATE ⚡` |
| 64–127 | `GOOD ✓` |
| ≥ 128 | `STRONG 🔒` |

---

## Компоненты TUI

### Тулбар (`#seq-toolbar`)
| Кнопка | ID | Действие |
|--------|----|----------|
| `▶ Capture` | `btn-seq-capture` | Начать захват токенов из Proxy |
| `■ Stop` | `btn-seq-stop` | Остановить захват |
| `⚡ Analyze` | `btn-seq-analyze` | Запустить анализ |
| `📂 Load File` | `btn-seq-load` | Загрузить токены из файла (1 на строку) |
| `🗑 Clear` | `btn-seq-clear` | Очистить всё |
| `📋 Copy` | `btn-seq-copy` | Скопировать сводку в буфер |

### Конфигурационная строка (`#seq-config-row`)
| Элемент | ID | Назначение |
|---------|----|-----------|
| Select | `#seq-source-select` | Источник: `Manual input` / `Proxy param` |
| Input | `#seq-param-input` | Имя параметра для захвата (напр. `sessionid`) |
| Static | `#seq-counter` | Счётчик: `Captured: N` |

### Горячие клавиши
| Клавиша | Действие |
|---------|----------|
| `Ctrl+Enter` | Запустить анализ |
| `Ctrl+L` | Очистить |

### Зоны
- **`#seq-input-col`** — `TextArea` (`#seq-token-area`): ввод токенов вручную, 1 токен на строку
- **`#seq-analysis-col`** — `RichLog` (`#seq-analysis-log`): результаты анализа
- **`#seq-gauge-area`** — визуальный gauge энтропии + вердикт + пояснение к битам

---

## Режимы захвата

### Manual input
Вставить токены вручную в TextArea (1 на строку) или загрузить из файла, затем нажать Analyze.

### Proxy param (live capture)
1. Выбрать источник `Proxy param` в селекте
2. Ввести имя параметра (напр. `session` или `csrf_token`)
3. Нажать `▶ Capture` — модуль подписывается на `ProxyRequestDoneEvent`
4. Трафик через прокси автоматически извлекает значение параметра из Cookie-заголовка
5. Нажать `■ Stop` для остановки захвата
6. Нажать `⚡ Analyze`

---

## Датаклассы модуля

```python
@dataclass
class SequencerReport:
    tokens: list[str]
    token_count: int
    avg_length: float
    min_length: int
    max_length: int
    charset_estimate: int       # оценочный размер алфавита
    mean_entropy: float         # средняя H бит/символ
    mean_total_bits: float      # среднее H * len
    effective_bits: float       # оценка реальной стойкости
    assessment: str             # WEAK ⚠️ / MODERATE ⚡ / GOOD ✓ / STRONG 🔒
    length_histogram: dict[int, int]  # len → count
    char_frequency: dict[str, int]    # char → count
    duplicates: int             # количество дублирующихся токенов

    def summary(self) -> str: ...           # однострочная сводка
    def rich_histogram(self, width=30) -> str: ...  # Rich-гистограмма длин
    def rich_charfreq(self, top_n=20) -> str: ...   # Top-N символов по частоте
```

---

## Публичный API

### Модуль `pentool.modules.sequencer`

```python
from pentool.modules.sequencer import Sequencer, token_entropy, charset_size

# Создать экземпляр
seq = Sequencer()
seq.on_token = lambda t: print(f"Got token: {t}")  # коллбэк при добавлении

# Добавить токены
seq.add_token("abc123def456")
seq.add_tokens_bulk(["token1", "token2", "token3"])
seq.add_from_text("token1\ntoken2\ntoken3")  # возвращает кол-во добавленных

# Извлечь из Cookie/заголовка
seq.extract_from_header("session=abc123; path=/", "session")  # → "abc123"

# Статистика
seq.count    # property: int
seq.tokens   # property: list[str] (копия)

# Анализ
report: SequencerReport = seq.analyze()
print(report.assessment)      # "STRONG 🔒"
print(report.effective_bits)  # 128.7
print(report.duplicates)      # 0
print(report.summary())

# Вспомогательные функции
entropy_bits_per_char = token_entropy("abc123")  # float
alphabet_size = charset_size("deadbeef")         # 16 (hex)

# Очистка
seq.clear()
```

### Публичный API экрана `SequencerScreen`

```python
# Добавить токен из внешнего источника (напр. из Proxy)
screen.add_token(token: str) -> None

# Программный запуск анализа
screen.action_analyze() -> None

# Очистка
screen.action_clear_tokens() -> None
```

---

## Известные проблемы / Исправленные баги

- Захват из Proxy (`proxy param`) извлекает токены из Cookie-заголовка входящих запросов; если токен приходит в теле ответа — нужен ручной ввод.
- При `on_unmount` захват автоматически останавливается (`_stop_capture()`), чтобы не оставлять подписки на EventBus.

---

## Чеклист ручного тестирования

### MVP
- [ ] Открыть Sequencer (Shift+Q) — экран отображается корректно
- [ ] Вставить в TextArea список токенов (1 на строку):
  ```
  a1b2c3d4e5f6a1b2
  f6e5d4c3b2a1f6e5
  1234567890ab1234
  ```
  Нажать `⚡ Analyze` — отображается отчёт
- [ ] `Ctrl+Enter` — то же что Analyze
- [ ] Summary-бар обновляется: Count / Avg Len / Charset / Entropy / Effective bits / [ASSESSMENT]
- [ ] Gauge меняет цвет: красный (WEAK <32 bit), жёлтый (MODERATE), зелёный (GOOD/STRONG)
- [ ] `Captured: N` в конфиг-строке обновляется после ввода токенов
- [ ] Проверить с дублями: добавить одинаковые токены → отчёт показывает `Duplicates: N`
- [ ] `📂 Load File` → диалог → загрузить файл с токенами (1/строку) → счётчик обновляется
- [ ] `📋 Copy` → сводка в буфере (без Rich-разметки)
- [ ] `🗑 Clear` / `Ctrl+L` — очищает textarea, лог, gauge, счётчик
- [ ] Gauge отображает прогресс-бар: `█████░░░░░ 64 bits`

### Proxy capture
- [ ] Запустить прокси, выбрать источник `Proxy param`, ввести `session` в поле Param
- [ ] Нажать `▶ Capture` — кнопка блокируется, активируется `■ Stop`
- [ ] Пропустить несколько запросов через прокси с Cookie `session=xxx` → счётчик растёт
- [ ] Нажать `■ Stop` → кнопки возвращаются в исходное состояние
- [ ] Нажать `⚡ Analyze` → отчёт по захваченным токенам

### DEMO (дополнительно)
- [ ] Слабые токены (`1`, `2`, `3`, `4`, `5`) → вердикт `WEAK ⚠️`, красный gauge
- [ ] Сильные токены (32-байтовые hex, напр. из `secrets.token_hex(32)`) → вердикт `STRONG 🔒`, зелёный gauge
- [ ] Гистограмма длин: смешанные длины токенов → видно распределение
- [ ] Топ символов по частоте (top-15) показывается в Analysis Log
- [ ] Пустой набор токенов → `INSUFFICIENT DATA` без ошибки
