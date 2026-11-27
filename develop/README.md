# Разработка: единственный вход

Всё, что касается разработки — планы, аудиты, решения, состояние, правила — живёт здесь.
`docs/` — только продуктовая документация для сайта, файлов про разработку там нет.

**Правило входа:** этот файл — единственный индекс. Появился новый документ — добавь строку
сюда. Документ закрыт и удалён — убери строку. Проверяется `tools/check_docs.py`.

## Что где

| Папка | Что лежит | Живёт |
|---|---|---|
| `plans/` | только то, что **ещё не сделано** | пункт выполнен → удаляется из плана, строка в [DONE.md](DONE.md); план без пунктов → удаляется целиком |
| `audits/` | аудиты, отчёты, снимки состояния: `ГГГГ-ММ-ДД-тема.md` | заморожены, не редактируются |
| `decisions/` | [ADR.md](decisions/ADR.md) — почему сделано именно так | только действующие решения |
| `state.md` | «что сейчас правда» | генерируется из `tools/facts.yml` |
| [rules.md](rules.md) | правила ведения этих документов | редко |
| [DONE.md](DONE.md) | журнал закрытого: одна строка на задачу | растёт |

## Документы

- [rules.md](rules.md) — правила ведения документации
- [conventions.md](conventions.md) — конвенции кода (что и как писать)
- [DONE.md](DONE.md) — что уже закрыто
- [state.md](state.md) — состояние проекта (сгенерировано)
- [decisions/ADR.md](decisions/ADR.md) — архитектурные решения

### Планы

- [plans/PLAN.md](plans/PLAN.md) — треки и приоритеты
- [plans/bugs-tui-2026-11-26.md](plans/bugs-tui-2026-11-26.md) — приёмка ТУИ владельцем (16 пунктов)
- [plans/tui-unification.md](plans/tui-unification.md) — унификация ТУИ, шаги 5.6+
- [plans/pre-release.md](plans/pre-release.md) — **что делать до релиза (рекомендация)**
- [plans/release.md](plans/release.md) — релиз v0.6.0 и профилирование
- [plans/backlog.md](plans/backlog.md) — идеи без приоритета
- [plans/modules.md](plans/modules.md) — модули и материалы
- [plans/common.md](plans/common.md) — инфраструктура и гварды
- [plans/pro-licensing.md](plans/pro-licensing.md) — PRO, оплата, лицензии
- [plans/intruder-autolimits.md](plans/intruder-autolimits.md) — авто-лимиты Intruder
- [plans/idea-ml-layer-distillation.md](plans/idea-ml-layer-distillation.md) — ML-слой (идея)
- [plans/idea-request-pipeline.md](plans/idea-request-pipeline.md) — труба запросов (идея)

### Аудиты и отчёты

- [audits/2026-11-26-tui-perf.md](audits/2026-11-26-tui-perf.md) — профилирование горячих путей
- [audits/2026-11-21-tui-report.md](audits/2026-11-21-tui-report.md) — реестр находок по ТУИ
- [audits/2026-11-21-tui-summary.md](audits/2026-11-21-tui-summary.md) — краткая версия
- [audits/2026-11-21-tui-audit.md](audits/2026-11-21-tui-audit.md) — предыдущая ревизия
- [audits/2026-11-17-pro-audit.md](audits/2026-11-17-pro-audit.md) — аудит PRO
- [audits/2026-11-24-handoff.md](audits/2026-11-24-handoff.md) — снимок состояния на 24 ноября
- [audits/2026-11-27-session-handoff.md](audits/2026-11-27-session-handoff.md) — передача смены: что закрыто, что дальше, грабли
