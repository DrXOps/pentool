# api

**Фасадный слой между доменными модулями, хранилищами и UI — единственная точка входа для TUI и CLI.**

- **Связи:** [[modules]], [[storage]], [[core]], [[tui]]
- **Код:** pentool/api/
- **Источник:** pentool/api/*.py, docs/API_CONTRACTS.md
- **Обновлено:** 2026-11-05

## Назначение

Инкапсулирует оркестрацию: связывает модуль (proxy, intruder, repeater…),
хранилище проекта и EventBus, отдавая UI/CLI простой асинхронный интерфейс.
Верхние слои не импортируют `pentool.modules.*` напрямую — это запрещено
`tools/check_layers.py` (`tui → modules`).

Реализует паттерн `ExportableAPI` — общий контракт экспорта скопированных
или сохранённых данных.

## Публичный интерфейс

- `ProxyAPI` — старт/стоп прокси, перехват, scope.
- `IntruderAPI` — атаки, per-tab состояние (`save_state`/`load_state`/`delete_tab`
  с `tab_uid`), результаты.
- `RepeaterAPI`, `TargetAPI`, `SpiderAPI` — соответствующие модули.
- `ExportableAPI` — базовый ABC с общим контрактом экспорта.
- Функциональные API без класса: `decoder_api` (`decode_op`, `decode_smart`,
  `encode_op`, `DecoderChain`, `OPERATIONS`), `comparer_api` (`compare`,
  `compare_lines`, `DiffResult`), `sequencer_api`.
- `payload_serialization.serialize_payloads` / `deserialize_payloads`.

`pentool.api` расширяет `__path__` через `pkgutil.extend_path`, чтобы PRO-код
(`pro/pentool/api/scanner_api.py`) подхватывался без изменения публичного пакета.

## Инварианты и подводные камни

- Все методы ввода-вывода асинхронные; синхронные обёртки — только в CLI.
- `intruder_api.save_state/load_state` требуют стабильный `tab_uid` — без него
  переключение вкладок перезапишет чужое состояние.
- PRO-модули (`scanner_api`, `scanner_tab_repository`) физически лежат в
  сабмодуле `pro` и в публичном репозитории отсутствуют.

## Связи

Зависит от [[modules]] и [[storage]]; используется [[tui]] и [[cli]];
расширяется PRO-кодом сабмодуля `pro`.

## Источник

`docs/API_CONTRACTS.md` (538 строк — контракты всех API-классов),
код `pentool/api/*.py`, коммит `cb11bfd`.
