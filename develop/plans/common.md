# Подплан: общие правки (инфраструктура, гварды, тесты, документация)

**Родитель:** [PLAN.md](../PLAN.md). **Обновлён:** 2026-11-27.

Только открытые общие задачи: инфраструктура, гварды, тесты, документация. Закрытое —
[../DONE.md](../DONE.md), порядок до релиза — [pre-release.md](pre-release.md).

## Открытое

### T-014. Тестовое покрытие виджетов и сервисов

- [ ] `tui/widgets/request_editor.py` (~30% → 60%)
- [ ] `tui/widgets/filter_bar_widget.py` (27% → 70%)
- [ ] `services/scan_service.py` (→ 60%)
- [x] `services/proxy_service.py` — путь записи в историю покрыт (`test_proxy_service_storage.py`, 7 тестов)

