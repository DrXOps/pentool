"""FilterableScreenMixin — подключает фильтрацию к Screen с DataTable.

Usage:
    class ProxyScreen(Screen, SortableTableMixin, FilterableScreenMixin):
        filter_bar_id = "filter-bar"

        def _reload_with_filter(self, spec: FilterSpec | None) -> None:
            if spec and not spec.is_empty:
                rows = await self._service.get_history(filters=spec)
            else:
                rows = await self._service.get_history()
            ...
"""

from __future__ import annotations

from typing import Any

from pentool.collections.filter_predicate import FilterSpec
from pentool.tui.widgets.filter_bar_widget import FilterBarWidget


class FilterableScreenMixin:
    """Миксин для экрана с фильтруемой таблицей.

    Требует:
        - self.filter_bar_id: str — DOM id FilterBarWidget
        - self._reload_with_filter(spec: FilterSpec | None) -> Awaitable[None]
    """

    filter_bar_id: str = ""
    _filter_spec: FilterSpec | None = None

    @property
    def current_filters(self) -> FilterSpec | None:
        """Текущий активный фильтр."""
        return self._filter_spec

    def _on_filter_changed(self, spec: FilterSpec) -> None:
        """Вызывается из обработчика FilterChanged.

        Сохраняет spec и запускает перезагрузку таблицы.
        """
        self._filter_spec = spec if not spec.is_empty else None
        self._scheduleFilterReload()

    def _scheduleFilterReload(self) -> None:
        """Запустить перезагрузку таблицы с текущим фильтром.

        Переопределяется в конкретном Screen (debounce, worker, etc).
        """
        raise NotImplementedError  # pragma: no cover

    def _get_filter_bar(self) -> FilterBarWidget | None:
        """Найти FilterBarWidget на экране."""
        if not self.filter_bar_id:
            return None
        try:
            return self.query_one(f"#{self.filter_bar_id}", FilterBarWidget)  # type: ignore[union-attr]
        except Exception:
            return None


class SqlFilterAdapter:
    """Адаптер: FilterSpec → SQL WHERE, совместимый со старыми storage.

    Используется в storage._build_where: если пришёл FilterSpec — конвертим,
    иначе — пустой WHERE.

    Usage:
        # в HttpStorage.get_history(filters=...):
        where, params = SqlFilterAdapter.build(filters)
    """

    @staticmethod
    def build(filters: FilterSpec | dict | None) -> tuple[str, list]:
        """Универсальный построитель WHERE.

        Accepts:
            FilterSpec — новый формат
            dict — legacy dict (больше не поддерживается, пустой WHERE)
            None — пустой WHERE
        """
        if isinstance(filters, FilterSpec):
            return filters.to_sql()
        # dict / None → пустой WHERE (обратная совместимость не нужна,
        # но пока storage не переписан, пусть компилируется)
        return "", []