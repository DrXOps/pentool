"""FilterBarBase — shared scaffolding for proxy & Intruder filter bars.

Both the proxy `FilterBar` and the Intruder `IntruderFilterBar` follow the
same shape: a row of filter Inputs/cyclers that, on Apply, are collected into
a dict and posted upward as a `FilterChanged`, and on Reset are cleared and
post an empty dict. `FilterBarBase` holds the cross-bar helpers so the two
bars don't each reimplement the query/reset dance.

Message dispatch note (critical Textual gotcha): `on_filter_bar_filter_changed`
/ `on_intruder_filter_bar_filter_changed` are magic method names derived from
the *message's class*. If a shared `FilterChanged` were inherited by both bars,
Textual would derive the handler name from the base class, silently turning
`on_filter_bar_filter_changed` into `on_filter_bar_base_filter_changed` and
breaking both screens. Every subclass therefore declares **its own**
`FilterChanged` Message; the base provides only the non-message plumbing.
"""

from __future__ import annotations

from textual.widget import Widget
from textual.widgets import Input


class FilterBarBase(Widget):
    """Reusable input read/reset plumbing for filter bars.

    Concrete bars subclass this, declare their own `FilterChanged` Message,
    and build their filters dict in `collect_filters()` (called on Apply) and
    clear their fields in `reset_all()` (called on Reset).
    """

    # Subclasses override and call super().emit(cls, filters).
    @staticmethod
    def _input_value(bar, selector: str) -> str:
        """Return the stripped text of an Input selected by *selector*.

        Duck-typed (any object exposing query_one with an `Input` class) so
        tests can inject a fake query_one. Returns "" on any lookup failure.
        """
        try:
            return str(bar.query_one(selector, Input).value).strip()
        except Exception:
            return ""

    @staticmethod
    def _set_input_value(bar, selector: str, value: str) -> None:
        """Set an Input's text, ignoring lookup failures (bar not mounted yet)."""
        try:
            bar.query_one(selector, Input).value = value
        except Exception:
            pass

    @staticmethod
    def emit(cls, bar, filters: dict) -> None:
        """Post a FilterChanged-message instance defined by *cls*.

        *cls* is the subclass's own nested Message class; *bar* is the widget
        instance (bar.post_message). Keeping both explicit avoids reaching
        into instance state that unit tests replace with fakes.
        """
        bar.post_message(cls(filters))

    def collect_filters(self) -> dict:
        """Build the filter dict for Apply. Subclasses override."""
        return {}

    def reset_all(self) -> None:
        """Clear every input this bar owns. Subclasses override."""
        return None
