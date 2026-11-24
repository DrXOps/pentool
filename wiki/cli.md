# cli

**Click-команды и headless-режим: запуск сканирования без TUI.**

- **Связи:** [[api]], [[core]], [[services]]
- **Код:** pentool/cli/
- **Источник:** pentool/cli/*.py, docs/CI_CD.md; правка сообщения о лицензии —
  изменения 2026-11-24
- **Обновлено:** 2026-11-24

## Назначение

Позволяет использовать Pentool в скриптах и CI: одна команда — один прогон,
результат в файл. Точка входа пакета — `pentool.__main__:main`. Лицензию CLI не
активирует: ключ вводят в интерфейсе (Settings → License → Activate), а CLI
лишь объясняет, где его взять.

## Публичный интерфейс

- `main.py` — корневая click-группа; `pentool --version`.
- `headless.py` — прогон без TUI.
- `scan.py`, `scan_runner.py` — скан цели с флагами
  (`--url`, `--check`, `--threads`, `--delay`, `--format`, `--output`).
- `project.py`, `proxy.py`, `ai_cmd.py` — проекты, прокси, AI-команды.
- `_SCANNER_UNAVAILABLE_MSG` (`scan_runner.py`) — единственный текст про
  лицензию в CLI: что делать, если PRO-сканер не установлен.

## Инварианты и подводные камни

- Коды выхода: `0` — успех, `1` — ошибка прогона, `2` — неверные аргументы
  (см. `docs/CI_CD.md`).
- **Подкоманды `pentool license` не существует.** `_SCANNER_UNAVAILABLE_MSG`
  раньше предлагал `pentool license trial` и `pentool license activate KEY` —
  команды, которых нет; тексты заменены на путь через Settings → License
  (ключ) и `support@pentool.pro` (триальный ключ по запросу).
- `test_cli_main.py::test_cli_version` исторически нестабилен при полном
  прогоне (проходит в изоляции) — см. [[CONTEXT]] → «Известные исключения».
- CLI не должен импортировать [[tui]]: запуск в headless не инициализирует
  Textual.

## Связи

Использует [[api]] и [[services]]; опирается на [[core]] (конфиг, лицензия).
Противоположность [[tui]] по способу взаимодействия: активация ключа и вход в
триал живут в [[tui]], CLI только ссылается на них текстом.

## Источник

Код `pentool/cli/*.py`, `docs/CI_CD.md` (флаги и коды выхода); коммит `cb11bfd`.
Правка `_SCANNER_UNAVAILABLE_MSG` — изменения 2026-11-24
`pentool/cli/scan_runner.py` от 2026-11-24; проверено: ни один файл
`pentool/cli/*.py` не объявляет команду `license`.
