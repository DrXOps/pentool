# pyperclip

**Копирование в системный буфер обмена.**

- **Связи:** [utils](../utils.md)
- **Код:** pyproject.toml → `[project].dependencies`
- **Источник:** pyproject.toml, импорты в коде
- **Обновлено:** 2026-11-05

## Зачем используется

Копирование в системный буфер обмена.

## Ограничения и заметки

На Linux требует xclip/xsel (`bin/xclip` в репозитории); см. `utils/copy_as.py`.

## Где используется

[[utils]]

## Источник

`pyproject.toml` (раздел `dependencies`), grep импортов по `pentool/`
и `pro/`; коммит `cb11bfd`.
