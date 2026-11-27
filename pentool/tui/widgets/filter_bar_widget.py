"""FilterBarWidget — a generic filter-row widget for any table.

Configured through inheritance:
    - configure() → list of FilterField (field descriptors)
    - compose() renders the fields defined by configure()
    - collect() reads the fields and builds a FilterSpec

A subclass must declare its own FilterChanged Message (see Textual naming).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

from pentool.collections.filter_predicate import FilterField, FilterFieldType, FilterPredicate, FilterSpec
from pentool.core.logging import get_logger
from pentool.tui.widgets.option_cycler import OptionCycler

logger = get_logger(__name__)

_TOGGLE_CSS = (Path(__file__).parent / "toggle_button.tcss").read_text(encoding="utf-8")
_FILTER_BAR_CSS = (Path(__file__).parent / "filter_bar_widget.tcss").read_text(encoding="utf-8")

# FilterBarWidget doesn't ship a DEFAULT_CSS — each concrete subclass
# (ProxyFilterBar, IntruderFilterBar) defines its own layout, widths,
# and styling. The base class only provides the widget tree via compose()
# and the filter-logic via configure()/collect().


class ToggleButton(Static):
    """Toggle button.

    Minimal DEFAULT_CSS for a basic appearance.
    Details (colors, hover, active) come from the parent CSS.
    """

    DEFAULT_CSS = _TOGGLE_CSS

    class Toggled(Message):
        def __init__(self, active: bool) -> None:
            super().__init__()
            self.active = active

    def __init__(self, label: str = "", active_label: str | None = None, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self._label = label
        self._active_label = active_label or label
        self._active: bool = False

    def is_active(self) -> bool:
        return self._active

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the button and grey it out when disabled."""
        self.set_class(not enabled, "disabled")

    def reset(self) -> None:
        self._active = False
        self.remove_class("-active")
        self.update(self._label)

    def toggle(self) -> None:
        self._active = not self._active
        self.set_class(self._active, "-active")
        self.update(self._active_label if self._active else self._label)
        self.post_message(self.Toggled(self._active))

    def on_click(self) -> None:
        self.toggle()


class FilterBarWidget(Widget):
    """Base filter-row widget.

    A subclass:
        1. Declares its own FilterChanged Message.
        2. Overrides configure() → list of FilterField.
        3. Calls super() in compose() to render the base, then its own widgets.
        4. Calls super() in collect() and extends it with custom predicates.
    """

    class FilterChanged(Message):
        def __init__(self, spec: FilterSpec) -> None:
            super().__init__()
            self.spec = spec

    DEFAULT_CSS = _FILTER_BAR_CSS

    #: Text of the two trailing buttons; the results bar overrides them.
    _apply_label = "Filter"
    _reset_label = "Clear"

    # ── Configuration ──────────────────────────────────────────────────────

    def configure(self) -> list[FilterField]:
        """Field descriptions for filtering. Override in a subclass."""
        return []

    # ── Compose ─────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield from self._compose_fields()
        yield from self._compose_actions()

    def _compose_fields(self) -> ComposeResult:
        """Label + control for every field from :meth:`configure`."""
        for f in self.configure():
            yield Label(f.label, classes="fb-label")
            yield from self._render_field(f)
            yield Label(" ", classes="fb-sep")

    def _compose_actions(self) -> ComposeResult:
        """The trailing buttons. Override to add toggles in front of them."""
        yield Button(self._apply_label, id="fb-apply", variant="primary")
        yield Button(self._reset_label, id="fb-reset")

    def _render_field(self, field: FilterField) -> ComposeResult:
        match field.field_type:
            case FilterFieldType.TEXT:
                yield Input(id=field.id, placeholder=field.placeholder, compact=True)
            case FilterFieldType.NUMBER:
                yield Input(id=field.id, placeholder=field.placeholder, type="integer", compact=True)
            case FilterFieldType.CYCLER:
                yield OptionCycler(id=field.id, options=field.options or [], allow_empty=True, suffix=" ▼")
            case FilterFieldType.TOGGLE:
                yield ToggleButton(field.label, id=field.id)
            case FilterFieldType.RANGE:
                lo_id = f"{field.id}-lo"
                hi_id = f"{field.id}-hi"
                yield Input(id=lo_id, placeholder=field.placeholder)
                yield Label("→", classes="fb-label")
                yield Input(id=hi_id, placeholder="∞")

    # ── Predicate collection ───────────────────────────────────────────────

    def collect(self) -> list[FilterPredicate]:
        """Read current UI values → FilterPredicates.

        A subclass may override this and extend the result of super().
        """
        predicates: list[FilterPredicate] = []
        for f in self.configure():
            raw = self._read_field(f)
            # An unticked toggle means "no constraint", not "field = False": a filter bar
            # that always filters is useless, and `error_count > False` is not a filter
            # anybody wrote. Ticked — the field is added with `value=True`.
            if f.field_type == FilterFieldType.TOGGLE and raw is False:
                continue
            if raw is not None and raw != "":
                predicates.append(
                    FilterPredicate(
                        field=f.field,
                        operator=f.operator,
                        value=self._normalize_value(f, raw),
                    )
                )
        return predicates

    def _read_field(self, field: FilterField) -> Any | None:
        try:
            match field.field_type:
                case FilterFieldType.TEXT | FilterFieldType.NUMBER:
                    return self.query_one(f"#{field.id}", Input).value.strip() or None

                case FilterFieldType.CYCLER:
                    return self.query_one(f"#{field.id}", OptionCycler).value

                case FilterFieldType.TOGGLE:
                    tb = self.query_one(f"#{field.id}", ToggleButton)
                    return tb.is_active()

                case FilterFieldType.RANGE:
                    lo = self.query_one(f"#{field.id}-lo", Input).value.strip()
                    hi = self.query_one(f"#{field.id}-hi", Input).value.strip()
                    if lo and hi:
                        return (lo, hi)
                    if lo:
                        return lo
                    return None
        except Exception:
            return None

    @staticmethod
    def _normalize_value(field: FilterField, raw: Any) -> Any:
        if field.field_type == FilterFieldType.NUMBER:
            try:
                return int(raw)
            except ValueError:
                return raw
        if field.field_type == FilterFieldType.RANGE and isinstance(raw, tuple):
            try:
                return (int(raw[0]), int(raw[1]))
            except ValueError:
                return raw
        return raw

    # ── Apply / Reset ──────────────────────────────────────────────────────

    def _apply(self) -> None:
        spec = FilterSpec(predicates=self.collect())
        self._emit(spec)

    def _reset(self) -> None:
        self._clear_fields()
        self._emit(FilterSpec())

    def _emit(self, spec: FilterSpec) -> None:
        self.post_message(self.FilterChanged(spec))

    def _clear_fields(self) -> None:
        for f in self.configure():
            self._clear_field(f)

    def _clear_field(self, field: FilterField) -> None:
        try:
            match field.field_type:
                case FilterFieldType.TEXT | FilterFieldType.NUMBER:
                    self.query_one(f"#{field.id}", Input).value = ""
                case FilterFieldType.CYCLER:
                    self.query_one(f"#{field.id}", OptionCycler).reset()
                case FilterFieldType.TOGGLE:
                    self.query_one(f"#{field.id}", ToggleButton).reset()
                case FilterFieldType.RANGE:
                    self.query_one(f"#{field.id}-lo", Input).value = ""
                    self.query_one(f"#{field.id}-hi", Input).value = ""
        except Exception as exc:
            # Filter field not cleared: after "Reset" the table stays
            # filtered by the previous value even though the bar looks empty.
            logger.debug("filter bar: field %r not cleared: %s", field.id, exc)

    # ── Handlers ───────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fb-apply":
            self._apply()
        elif event.button.id == "fb-reset":
            self._reset()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in any Input applies the filter."""
        self._apply()

    def on_option_cycler_changed(self, event: OptionCycler.Changed) -> None:
        """Clicking a cycler re-applies at once — no separate Apply needed."""
        self._apply()
