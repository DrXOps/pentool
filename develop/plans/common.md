# Подплан: общие правки (инфраструктура, гварды, тесты, документация)

**Родитель:** [PLAN.md](../PLAN.md). **Обновлён:** 2026-11-23.

То, что не относится к конкретному модулю, но влияет на весь проект.

## Закрыто (для ориентира)

- Комментарии и докстринги на английском: `check_english_comments` — 0 строк в 0
  файлах, база пуста (2026-11-23). Гвард оставлен, новый русский комментарий роняет
  коммит; цитата в комментарии помечается `# i18n-ok:`.
- Логирование: уровни по последствию (ADR-6), ротация журнала, DEBUG на горячем пути,
  трещотки `check_broad_except` / `check_silent_except` / `check_logging_policy`.
- Гварды структуры: `check_tui_css` (592 селектора сверяются с DOM),
  `check_lazy_screens`, `check_layers`, `review_new_files`, `test_on_selectors_resolve`,
  `test_handler_name_dispatch`, `test_app_mixin_surface`, `test_dialogs_unified`,
  `test_filter_bar_unified`.
- Краш-репортинг из TUI (источник `tui` в payload `/api/crash`).

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

### Чистка документации (сделано 2026-11-23, см. PLAN.md)

- удалены: 4 файла сессий, `plan_tabs_repeater_intruder`, `plan-features-2026-11-23`,
  `plan-recon-integration`, `plan-release-2026-11-20`, `tasks-pentool` (переехали в
  подпланы и `tech_debt.md`);
- `docs/tui-audit/`: оставлены `DECISIONS.md` (ADR) и `CONVENTIONS.md` (правила),
  удалены `REPORT.md`, `SUMMARY.md`, `COMPONENTS.md` (исторические находки, устарели
  после редизайна); ссылки в `pentool/tui/README.md` обновлены;
- `docs/audit/`: оставлен свежий `2026-11-21-tui-audit.md` и
  `pro-audit-2026-11-17.md`; удалены сентябрьские и ноябрьские исторические аудиты;
  индекс `README.md` переписан.
