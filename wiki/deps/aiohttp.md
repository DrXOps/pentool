# aiohttp

**Асинхронный HTTP-клиент: прокси-трафик, лицензии, обновления, crash-report.**

- **Связи:** [utils](../utils.md), [core](../core.md)
- **Код:** pyproject.toml → `[project].dependencies`
- **Источник:** pyproject.toml, импорты в коде
- **Обновлено:** 2026-11-05

## Зачем используется

Асинхронный HTTP-клиент: прокси-трафик, лицензии, обновления, crash-report.

## Ограничения и заметки

Основной транспорт `utils/http_client.py`; поддержка override-резолвера для DNS bypass.

## Где используется

[[utils]], [[core]]

## Источник

`pyproject.toml` (раздел `dependencies`), grep импортов по `pentool/`
и `pro/`; коммит `cb11bfd`.
