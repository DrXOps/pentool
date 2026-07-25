# Decoder — Документация модуля

## Статус: 🚧 Код написан, не проверено вручную

**Файлы:**
- `pentool/modules/decoder.py` — бизнес-логика (19 операций)
- `pentool/tui/screens/decoder/screen.py` — TUI
- `pentool/tui/screens/decoder/screen.tcss` — CSS
- `tests/unit/modules/test_decoder.py` — 53 теста (все зелёные)

**Горячая клавиша:** `Shift+D`

---

## Операции (19 штук)

| Операция | Направление | Тип |
|----------|-------------|-----|
| URL Encode / Decode | encode/decode | Обратимая |
| Base64 Encode / Decode | encode/decode | Обратимая |
| Base64URL Encode / Decode | encode/decode | Обратимая |
| HTML Encode / Decode | encode/decode | Обратимая |
| Hex Encode / Decode | encode/decode | Обратимая |
| Unicode Encode / Decode | encode/decode | Обратимая |
| JWT Decode | decode only | Необратимая (показывает header+payload) |
| Gzip+B64 Encode / Decode | encode/decode | Обратимая |
| MD5 | hash | Необратимая |
| SHA1 | hash | Необратимая |
| SHA256 | hash | Необратимая |
| SHA512 | hash | Необратимая |

---

## Публичный API (модуль)

```python
from pentool.modules.decoder import (
    OP_LABELS,          # list[str] — все 19 операций
    encode_op,          # (operation: str, text: str) -> str
    run_chain,          # (operations: list[str], text: str) -> (result, steps)
    decode_smart,       # (text: str) -> str — авто-определение кодировки
    DecoderChain,       # dataclass с .add/.remove/.clear/.run
)
```

---

## TUI — интерфейс

**Тулбар:** `▶ Run` | `+ Add Step` | `✗ Clear Chain` | `⇅ Swap I/O` | `📋 Copy` | `🔍 Smart`

**Строка операции:** Select с 19 операциями + отображение текущей цепочки

**Рабочая область:**
- Input (левый TextArea) → Output (правый TextArea)
- Steps Log (нижний RichLog) — показывает промежуточные результаты

**Цепочки:** выбрать операцию → `Add Step` → цепочка накапливается → `Run` применяет последовательно

**Smart decode:** автоматически определяет URL/Base64/Hex/JWT/HTML

---

## Чеклист ручного тестирования

### MVP
- [ ] Открытие модуля через `Shift+D` или вкладку
- [ ] Ввод текста в Input → Run без цепочки → применяется выбранная операция
- [ ] Base64 Encode: `Hello` → `SGVsbG8=`
- [ ] Base64 Decode: `SGVsbG8=` → `Hello`
- [ ] URL Encode: `hello world` → `hello%20world`
- [ ] MD5: `hello` → `5d41402abc4b2a76b9719d911017c592`
- [ ] JWT Decode: корректно показывает header+payload в JSON
- [ ] Добавить 2+ шага в цепочку → Run → Steps Log показывает промежуточные значения
- [ ] `⇅ Swap I/O` — меняет Input и Output местами
- [ ] `✗ Clear Chain` — очищает цепочку
- [ ] `📋 Copy` — копирует Output в буфер обмена
- [ ] `🔍 Smart` на Base64-строке → правильно декодирует
- [ ] `🔍 Smart` на URL-строке (`%20`) → правильно декодирует
- [ ] `🔍 Smart` на JWT → показывает JSON

### DEMO (дополнительно)
- [ ] Цепочка из 3+ операций работает корректно
- [ ] Ошибочная операция на неподходящем входе → показывает `[error: ...]` в steps, не падает
- [ ] Roundtrip Base64 → URL → URL Decode → Base64 Decode возвращает оригинал
