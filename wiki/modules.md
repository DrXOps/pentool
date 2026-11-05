# modules

**Независимая от интерфейса доменная логика инструмента: proxy, repeater, intruder, spider, decoder, comparer, sequencer, target.**

- **Связи:** [[api]], [[services]], [[proxy]], [[core]], [[utils]]
- **Код:** pentool/modules/
- **Источник:** pentool/modules/*.py, docs/USER_GUIDE.md
- **Обновлено:** 2026-11-05

## Назначение

Реализует сами атаки и обработку трафика без знания о TUI. Правило слоёв:
`modules` не импортирует `tui`, `api`, `cli` — общение идёт через [[api]].
PRO-надстройки (`scanner/`, `intruder_turbo.py`) лежат в сабмодуле `pro/`
и подхватываются через `pkgutil.extend_path`.

## Публичный интерфейс

- **Intruder** — `AttackType` (Sniper, Battering Ram, Pitchfork, Cluster Bomb),
  `IntruderConfig`, `IntruderAttack`, `IntruderResult`; источники payload'ов:
  `FilePayloadSource`, `NumericPayloadSource`, `CharPayloadSource`,
  `ChainedPayloadSource`, `ProcessedPayloads`.
- **Repeater** — `Repeater`, `RepeaterEntry` (сохраняется в SQLite).
- **Match & Replace** — `MatchReplaceRule`, `MatchReplaceEngine`.
- **Decoder** — `DecoderChain` (19 операций, цепочки).
- **Comparer** — `DiffLine`, `CompareStats`, `DiffResult`.
- **Sequencer** — `SequencerReport`, `FIPSTestResult` (FIPS-тест энтропии).
- **Proxy** — `ProxyServer` (реализация; процесс-обёртка — в [[proxy]]).
- **Target** — `SiteMap` (hosts, scope).
- **Spider**, **WebSocket** — обход и перехват WS-кадров.

## Инварианты и подводные камни

- **`AttackType` определяет, как комбинируются payload-наборы**; Cluster Bomb
  даёт декартово произведение и взрывается по числу запросов.
- `SiteMap.save()` пишет в SQLite **на том же соединении**, что и узлы карты
  (`self._db`). Раньше wildcard-правила scope сохранялись через
  `db_schema.set_project_setting()`, которая открывала второе `aiosqlite`
  соединение к тому же файлу и конкурировала за write-lock с уже открытой
  транзакцией — `database is locked`, проглоченный `except` в `save()`, то
  есть scope не сохранялся вовсе. Второе соединение в `save()`/`load()`
  добавлять нельзя: на файле должна быть одна пишущая транзакция
  (тест `test_target.py::test_save_and_load`).
- PRO-проверки сканера фильтруются по лицензии через `required_feature`
  (см. [[core]]) — на free-плане движок возвращает пустой список задач.

## Связи

Опирается на [[utils]] и [[core]]. Используется через [[api]]; сервисный
слой [[services]] оркестрирует вызовы. `ProxyServer` разворачивается в
отдельном процессе — см. [[proxy]].

## Источник

Код `pentool/modules/*.py`, `docs/USER_GUIDE.md` (разделы Intruder,
Repeater, Decoder, Comparer, Sequencer, Spider), коммит `cb11bfd`.
