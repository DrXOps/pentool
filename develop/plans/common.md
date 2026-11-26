# Подплан: общие правки (инфраструктура, гварды, тесты, документация)

**Родитель:** [PLAN.md](../PLAN.md). **Обновлён:** 2026-11-27.

Только открытые общие задачи: инфраструктура, гварды, тесты, документация. Закрытое —
[../DONE.md](../DONE.md), порядок до релиза — [pre-release.md](pre-release.md).

## Открытое

### T-014. Тестовое покрытие виджетов и сервисов

- [ ] `tui/widgets/request_editor.py` (~30% → 60%)
- [ ] `tui/widgets/filter_bar_widget.py` (27% → 70%)
- [ ] `services/scan_service.py`, `services/proxy_service.py` (→ 60%)

### T-022. Переводы документации: раздел «Запуск в Windows через WSL2»

`docs/i18n/hi/INSTALLATION.md` и `docs/i18n/zh/INSTALLATION.md` содержат указатель на
английский гайд (88 строк на язык). Нужно перевести, убрать вставку «translation of
this section is pending», проверить самодостаточность и якоря.

### T-024 (остаток). `DEFAULT_CONFIG_DIR` из конфига

`--config` теперь становится конфигом процесса (`set_config`), но
`_project_path_for_target` и `DEFAULT_CONFIG_DIR` по-прежнему указывают на
`~/.config/pentool/projects` — для полной изоляции прогонов их тоже нужно выводить
из конфига.

