# services

**Оркестрационный слой между доменными модулями и TUI: запуск, состояние, фоновые задачи.**

- **Связи:** [[modules]], [[api]], [[core]]
- **Код:** pentool/services/
- **Источник:** pentool/services/*.py; реестр AI-задач — изменения
  2026-11-24
- **Обновлено:** 2026-11-24

## Назначение

Связывает асинхронные модули с UI-потоком: держит состояние запуска,
транслирует события через EventBus, управляет жизненным циклом прогонов.

## Публичный интерфейс

- `BaseService` — общий жизненный цикл.
- `ProxyService`, `RepeaterService`, `IntruderService`, `ScanService`
  (`ScanConfig` — параметры прогона).
- `TechDetector` — определение стека технологий по ответам.
- `services/ai/` — интеграция с AI: `AIBackend` (ABC), `MCPBackend`
  (`provider.py`), `AITask`, `factory.py`, `prompts.py`, `audit_log.py`.
- `prompts.REGISTRY` (`dict[str, AITask]`) — контракт между вызывающим кодом и
  промтами: `xss_waf_bypass`, `choose_checks`, `crawl_endpoints`,
  `finding_analysis`, `generate_payloads`, `prioritize_params`, `discovery`.
  `discovery` — одна задача на всю разведку: инструкция (субдомены, эндпоинты,
  real IP, фаззинг) приходит в `context`, ответ — JSON-массив имён или объектов
  `{"method", "path"}`.

## Инварианты и подводные камни

- **Любой литерал `generate("<name>")` обязан быть в `REGISTRY`.**
  `MCPBackend.generate()` берёт задачу через `REGISTRY.get()` и на промахе
  пишет warning и возвращает `None` — вызывающий код тихо получает «пусто».
  Так разведка (Recon) звала задачу `discovery`, которой в реестре не было:
  warning уходил в лог, а AI-половина разведки возвращала пустой результат.
  Сторож — `tests/unit/services/test_ai_task_registry.py`: сканирует
  `pentool/` и `pro/pentool/` на литералы `.generate("…")` и сверяет с реестром.
- Сервисы удерживают «живые» объекты между Stop и Resume — тот же экземпляр
  движка переиспользуется для продолжения сканирования.
- AI-бэкенд вынесен за фабрику (`factory.py`): наличие MCP-сервера не должно
  ломать запуск без него.

## Связи

Опирается на [[modules]] и [[core]]; вызывается из [[api]] и [[tui]].
Обратная сторона контракта `REGISTRY` — PRO-модули разведки
(`pro/pentool/modules/ai_discovery/{runner,subdomain,endpoint,real_ip,param_fuzzer}.py`):
они формируют текст инструкции сами и передают его через `context`, поэтому
задача одна на четыре сценария.

## Источник

Код `pentool/services/`; коммит `cb11bfd`. Задача `discovery` в
`pentool/services/ai/prompts.py` — изменения 2026-11-24 от 2026-11-24;
симптом до правки (warning «неизвестная задача» и `None` из
`MCPBackend.generate`) описан в комментарии перед регистрацией задачи.
