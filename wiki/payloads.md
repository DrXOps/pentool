# payloads

**YAML-наборы payload'ов для проверок сканера (SQLi, XSS, SSTI, LFI, RCE, SSRF, XXE, open redirect, заголовки).**

- **Связи:** [[modules]], [[deps/pyyaml]]
- **Код:** pentool/payloads/
- **Источник:** pentool/payloads/*.yaml
- **Обновлено:** 2026-11-05

## Назначение

Данные, а не код: наборы payload'ов вынесены в YAML, чтобы их можно было
править без изменения Python-логики. Читаются через
`pentool.modules.scanner.payloads.load_payloads(<name>)` (PRO-модуль).

## Публичный интерфейс

Наборы файлов (по одному на класс проверки):

- `sqli.yaml`, `xss.yaml`, `ssti.yaml`, `lfi.yaml`, `rce.yaml`,
  `ssrf.yaml`, `xxe.yaml`, `open_redirect.yaml`, `headers.yaml`.

Общая структура: `name`, `type`, `description`, `detection`, `signatures`
и список payload'ов.

## Инварианты и подводные камни

- **`lfi.yaml` не читается на этом рабочем каталоге.** Windows Defender
  блокирует доступ к файлу из-за webshell-строк (`php://input`,
  `expect://`, `data://…base64`): чтение завершается `EINVAL`. Файл в
  git-индексе цел (blob `53a2c35f`), но из WSL через 9p его не открыть.
  Тесты, читающие его, на этой машине падают/пропускаются — см.
  [[CONTEXT]] → «Известные исключения».
- Наборы — **данные**: не добавляйте туда Python-выражения.
- `get_payloads()` кэшируется в памяти (см. `modules/scanner/payloads.py`),
  поэтому правки YAML в работающем процессе не подхватятся до перезапуска.

## Связи

Потребляются [[modules]] (PRO-проверки сканера). Парсинг YAML — через
[[deps/pyyaml]].

## Источник

Файлы `pentool/payloads/*.yaml`; git-индекс (blob `lfi.yaml` =
`53a2c35f920e50fa4e19f7ea7a71ee3983473614`); коммит `cb11bfd`.
