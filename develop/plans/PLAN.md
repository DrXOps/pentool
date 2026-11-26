# План работ

Только то, что **не сделано**. Сделанное — в [../DONE.md](../DONE.md), состояние проекта —
[../state.md](../state.md). Правила ведения — [../rules.md](../rules.md).

## Сейчас в работе

| Что | План | Осталось |
|---|---|---|
| Унификация ТУИ | [tui-unification.md](tui-unification.md) | шаг 6 (Proxy: общий конвейер истории), 7–10 |
| Приёмка ТУИ владельцем | [bugs-tui-2026-11-26.md](bugs-tui-2026-11-26.md) | 4 пункта + 3 «проверить вручную» |
| Очередь ТУИ и отзывчивость | [tui.md](tui.md) | T-030 ч.2, профилирование |
| Релиз v0.6.0 | [release.md](release.md) | гейт: профилирование снято, остались мерж и тег |

## Ждёт приоритета

- [tech_debt.md](tech_debt.md) — технический долг (мелкое, но накопленное);
- [pro-licensing.md](pro-licensing.md) — PRO: остался `/api/pro/version` (503) и продвижение;
- [modules.md](modules.md) — модули и материалы;
- [common.md](common.md) — инфраструктура и гварды;
- [intruder-autolimits.md](intruder-autolimits.md) — авто-лимиты вместо Turbo;
- [backlog.md](backlog.md) — идеи без приоритета;
- [idea-ml-layer-distillation.md](idea-ml-layer-distillation.md) — ML-слой;
- [idea-request-pipeline.md](idea-request-pipeline.md) — труба запросов.

## Правила

1. Пункт сделан → удаляется из плана, одна строка в [../DONE.md](../DONE.md).
2. План без пунктов → удаляется, ссылка уходит из [../README.md](../README.md).
3. Правка кода и правка плана — одним коммитом.
