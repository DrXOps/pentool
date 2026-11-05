# pyyaml

**Чтение конфигурации и YAML-наборов payload'ов.**

- **Связи:** [core](../core.md), [payloads](../payloads.md)
- **Код:** pyproject.toml → `[project].dependencies`
- **Источник:** pyproject.toml, импорты в коде
- **Обновлено:** 2026-11-05

## Зачем используется

Чтение конфигурации и YAML-наборов payload'ов.

## Ограничения и заметки

Используется в `core/config.py` и PRO-модуле `scanner/payloads.py`.

## Где используется

[[core]], [[payloads]]

## Источник

`pyproject.toml` (раздел `dependencies`), grep импортов по `pentool/`
и `pro/`; коммит `cb11bfd`.
