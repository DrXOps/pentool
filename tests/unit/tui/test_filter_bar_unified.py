"""One cycler, one filter-bar CSS — F-020 and F-021.

F-020: ``filter_bar_widget.Cycler`` and ``widgets/option_cycler.OptionCycler``
were near-identical click-to-cycle toggles. Both kept an index and posted a
``Changed`` message; ``Cycler`` had no CSS of its own (its look depended on
which filter bar happened to be its parent), no ``control`` property, so
``@on(...)`` selectors could not address it, and a different message
signature. It is now gone; `OptionCycler` grew ``allow_empty``/``suffix``.

F-021: ``WsFilterBar.DEFAULT_CSS`` was built as
``proxy_filter_bar.tcss`` with ``.replace("ProxyFilterBar", "WsFilterBar")``
plus two appended rules. Renaming the base class would silently have renamed
half of ``WsFilterBar``'s stylesheet with it. Both bars now share
``HistoryFilterBar`` and one stylesheet that names that class.

The guards are structural: a second cycler class and a ``.replace``-built
stylesheet are refused by scanning the source, so the pattern cannot come back
by copy-paste.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from textual.css.query import NoMatches
from textual.widgets import Static

from pentool.tui.widgets import filter_bar_widget
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.proxy_filter_bar import HistoryFilterBar, ProxyFilterBar, WsFilterBar

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"


# ── F-020: OptionCycler absorbed Cycler ─────────────────────────────────────


def test_cycler_class_is_gone() -> None:
    assert not hasattr(filter_bar_widget, "Cycler"), (
        "Cycler must not come back — OptionCycler (allow_empty/suffix) covers it"
    )


def test_filter_bar_renders_option_cycler() -> None:
    from pentool.collections.filter_predicate import FilterField, FilterFieldType, FilterOp

    field = FilterField(
        "fb-x",
        "X:",
        FilterFieldType.CYCLER,
        "x",
        FilterOp.IN,
        options=[("Any", ""), ("GET", "GET")],
    )
    bar = object.__new__(filter_bar_widget.FilterBarWidget)
    (widget,) = list(bar._render_field(field))
    assert isinstance(widget, OptionCycler)


def test_allow_empty_makes_first_option_the_any_slot() -> None:
    cycler = OptionCycler([("Any", ""), ("GET", "GET")], allow_empty=True, suffix=" ▼")
    assert cycler.value == ""
    cycler.on_click()
    assert cycler.value == "GET"
    cycler.reset()
    assert cycler.value == ""


def test_without_allow_empty_the_value_is_what_the_option_says() -> None:
    """Settings' theme cycler: option 0 is a real value, not an "Any" slot."""
    cycler = OptionCycler([("Dark", "dark"), ("Light", "light")])
    assert cycler.value == "dark"


def test_suffix_lands_in_the_rendered_label() -> None:
    rendered: list[str] = []
    cycler = OptionCycler([("Any", ""), ("GET", "GET")], allow_empty=True, suffix=" ▼")
    cycler.update = lambda text: rendered.append(text)  # type: ignore[method-assign]
    cycler.reset()
    assert rendered[-1] == "Any ▼"


# ── F-021: one stylesheet, no .replace ─────────────────────────────────────


def test_both_bars_share_the_same_stylesheet() -> None:
    assert ProxyFilterBar.DEFAULT_CSS == WsFilterBar.DEFAULT_CSS
    assert ProxyFilterBar.DEFAULT_CSS == HistoryFilterBar.DEFAULT_CSS
    assert issubclass(ProxyFilterBar, HistoryFilterBar)
    assert issubclass(WsFilterBar, HistoryFilterBar)


def test_stylesheet_names_the_shared_base() -> None:
    css = ProxyFilterBar.DEFAULT_CSS
    assert "HistoryFilterBar" in css
    assert "ProxyFilterBar" not in css and "WsFilterBar" not in css


def test_no_replace_built_stylesheet_in_the_tui() -> None:
    """A ``.read_text(...).replace(...)`` stylesheet is a rename trap."""
    offenders: list[str] = []
    for path in sorted(_TUI.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
                # Only flag it when it hangs off a read_text() call: that is the
                # "generate a stylesheet by string surgery" shape.
                inner = node.func.value
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "read_text"
                ):
                    offenders.append(f"{path.relative_to(_TUI.parent.parent)}:{node.lineno}")
    assert not offenders, "build DEFAULT_CSS from a real .tcss, do not .replace() a class name:\n  " + "\n  ".join(
        offenders
    )


def test_dead_filter_bar_stylesheet_is_deleted() -> None:
    """``filter_bar.tcss`` was a stale copy of the proxy bar's stylesheet."""
    assert not (_TUI / "widgets" / "filter_bar.tcss").exists()


@pytest.mark.parametrize("bar", [ProxyFilterBar, WsFilterBar], ids=lambda c: c.__name__)
def test_bar_renders_scope_and_comments_toggles(bar: type[HistoryFilterBar]) -> None:
    instance = object.__new__(bar)
    rendered = list(instance.compose())
    ids = {getattr(w, "id", None) for w in rendered}
    assert {"fb-scope", "fb-comments", "fb-apply", "fb-reset"} <= ids


def test_ws_bar_still_pins_websocket_only() -> None:
    bar = object.__new__(WsFilterBar)
    # Молчание тоглов — ровно `NoMatches`: виджета нет в дереве. Раньше здесь
    # стоял `LookupError`, и это скрывало, что бар ловил вообще всё (ADR-6 п.4).
    bar.query_one = lambda *a, **k: (_ for _ in ()).throw(NoMatches())  # type: ignore[method-assign]
    fields = bar.collect()
    assert any(p.field == "is_websocket" for p in fields)


def test_cycler_clicks_apply_the_filter_without_a_button_press() -> None:
    """``Cycler`` used to reach the bar through ``on_cycler_changed`` on the bar."""
    bar = object.__new__(filter_bar_widget.FilterBarWidget)
    applied: list[bool] = []
    bar._apply = lambda: applied.append(True)  # type: ignore[method-assign]
    bar.on_option_cycler_changed(OptionCycler.Changed(OptionCycler([("A", "a")]), "a"))
    assert applied == [True]


def test_toggle_button_is_still_a_static_subclass() -> None:
    """Guard against a careless import replacement in this module."""
    assert issubclass(filter_bar_widget.ToggleButton, Static)
