"""TabRenameMixin — двойной клик по вкладке → inline переименование."""

from __future__ import annotations

from textual.events import Click
from textual.widgets import Input, Tab, TabbedContent

from pentool.core.logging import get_logger

_log = get_logger(__name__)


class TabRenameMixin:

    _rename_input_id: str = "rename-input"
    _rename_tab_prefix: str = ""
    _rename_tabs_widget_id: str = ""

    def on_click(self, event: Click) -> None:
        """Двойной Click на Tab (chain=2) → переименование."""
        if event.chain < 2:
            return

        widget = event.widget
        _log.debug("TabRenameMixin.on_click: chain=%d widget=%r type=%s",
                   event.chain, widget, type(widget).__name__)

        if not isinstance(widget, Tab):
            return

        # Определяем pane_id из tab.id: "--content-tab-{pane_id}"
        tab_widget_id = widget.id or ""
        pane_id = tab_widget_id.removeprefix("--content-tab-")

        _log.debug("TabRenameMixin: pane_id=%r prefix=%r", pane_id, self._rename_tab_prefix)

        # Фильтр по префиксу
        if self._rename_tab_prefix and not pane_id.startswith(self._rename_tab_prefix):
            _log.debug("TabRenameMixin: pane_id %r не совпадает с префиксом %r", pane_id, self._rename_tab_prefix)
            return

        # Фильтр: Tab должен быть внутри нашего TabbedContent
        if self._rename_tabs_widget_id:
            try:
                tc = self.query_one(  # type: ignore[attr-defined]
                    f"#{self._rename_tabs_widget_id}", TabbedContent
                )
                ancestor = widget.parent
                found = False
                while ancestor is not None:
                    if ancestor is tc:
                        found = True
                        break
                    ancestor = getattr(ancestor, "parent", None)
                if not found:
                    _log.debug("TabRenameMixin: Tab не является потомком %r", self._rename_tabs_widget_id)
                    return
            except Exception as e:
                _log.debug("TabRenameMixin: ошибка поиска TabbedContent: %s", e)
                return

        _log.debug("TabRenameMixin: DOUBLE CLICK → _start_rename(%r)", pane_id)
        event.stop()
        self._start_rename(pane_id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != self._rename_input_id:
            return
        tab_id = getattr(event.input, "_rename_tab_id", None)
        new_name = event.value.strip()
        event.input.display = False
        if tab_id and new_name:
            self._rename_tab(tab_id, new_name)

    def on_input_blur(self, event) -> None:
        try:
            inp = self.query_one(  # type: ignore[attr-defined]
                f"#{self._rename_input_id}", Input
            )
            if inp.display:
                inp.display = False
        except Exception:
            pass

    def _start_rename(self, tab_id: str) -> None:  # type: ignore[empty-body]
        raise NotImplementedError

    def _rename_tab(self, tab_id: str, new_name: str) -> None:  # type: ignore[empty-body]
        raise NotImplementedError
