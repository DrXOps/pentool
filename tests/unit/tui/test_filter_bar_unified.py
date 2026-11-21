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
from textual.app import App
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Button, Static

from pentool.tui.app import PentoolApp
from pentool.tui.widgets import filter_bar_widget
from pentool.tui.widgets.option_cycler import OptionCycler
from pentool.tui.widgets.proxy_filter_bar import HistoryFilterBar, ProxyFilterBar, WsFilterBar
from pentool.tui.widgets.toolbar_button import ToolbarButton

_TUI = Path(__file__).resolve().parents[3] / "pentool" / "tui"
_APP_CSS = (_TUI / "app.tcss").read_text(encoding="utf-8")


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


@pytest.mark.asyncio
@pytest.mark.parametrize("bar", [ProxyFilterBar, WsFilterBar], ids=lambda c: c.__name__)
async def test_bar_renders_scope_and_comments_toggles(bar: type[HistoryFilterBar]) -> None:
    """Toggles and buttons must be in the tree after a real mount.

    The bar composes fields, toggles and actions, and as soon as any container
    appears a "flat list of compose() output" proves nothing — it only sees the
    containers. The test mounts the bar into an empty app and checks ids across
    the whole tree.
    """

    class _Host(App):
        def compose(self):
            yield bar(id="filter-bar")

    app = _Host()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        ids = {widget.id for widget in app.query("*") if widget.id}
    assert {"fb-scope", "fb-comments", "fb-apply", "fb-reset"} <= ids


async def _clipped_controls(
    bar: type[HistoryFilterBar],
    width: int,
    *,
    shrink: bool = False,
) -> dict[str, object]:
    """Render the bar at ``width`` and report the controls past the card edge.

    ``shrink=True`` emulates the real path: mount wide, then shrink the terminal
    so the bar gets a genuine Resize (hand-setting the screen class is *not*
    enough — the width change then arrives without any resize event).

    Everything is read inside the running app — the widgets are unmounted by the
    time the ``async with`` block ends.
    """
    breakpoint = PentoolApp.NARROW_BREAKPOINT

    class _Host(App):
        # The real app.tcss is loaded so the card frame/padding and the window
        # frame apply as they do in the app: `#app-shell` spends columns on its
        # border (plus padding when the terminal is not narrow), and `.card` adds
        # a border and one column of padding per side.
        CSS = (
            _APP_CSS
            + """
        #table-area { height: 1fr; width: 1fr; }
        #filter-bar { height: auto; }
        """
        )

        def compose(self):
            with Vertical(id="app-shell"):
                with Vertical(id="table-area"):
                    yield bar(id="filter-bar", classes="card")

        def on_resize(self, event) -> None:
            self.screen.set_class(event.size.width < breakpoint, "narrow")

    app = _Host()
    start = max(width, breakpoint) if shrink else width
    async with app.run_test(size=(start, 20)) as pilot:
        await pilot.pause()
        if shrink:
            await pilot.resize_terminal(width, 20)
            await pilot.pause()
        mounted = app.query_one("#filter-bar")
        avail = mounted.content_region.width
        # Controls live in the two `.fb-row` containers; clipping is decided per
        # row, because a row is what overflows.
        clipped: list[str] = []
        need = 0
        for row in mounted.children:
            row_need = max((child.region.right for child in row.children), default=0)
            need = max(need, row_need)
            clipped += [child.id or child.__class__.__name__ for child in row.children if child.region.right > avail]
        apply_button = mounted.query_one("#fb-apply", Button)
        reset_button = mounted.query_one("#fb-reset", Button)
        result: dict[str, object] = {
            "clipped": clipped,
            "need": need,
            "avail": avail,
            "two_rows": mounted.is_two_rows,
            "apply_label": str(apply_button.label),
            "reset_label": str(reset_button.label),
            "scope_label": str(mounted.query_one("#fb-scope", ToolbarButton).label),
            "comments_label": str(mounted.query_one("#fb-comments", ToolbarButton).label),
        }
    # The bar must not be wider than the card it sits in — and the card must not be
    # wider than the terminal. Exact margins depend on the window frame (border +
    # optional padding) and the card (border + padding), so the guard checks the
    # invariant instead of hardcoding cell counts that drift with the CSS.
    assert 0 < avail < width, "the bar got the full terminal width — card/window chrome is not applied"
    assert avail >= width - 10, f"bar lost too much width to chrome: {avail} of {width}"
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("bar", [ProxyFilterBar, WsFilterBar], ids=lambda c: c.__name__)
async def test_bar_controls_fit_120_columns(bar: type[HistoryFilterBar]) -> None:
    """Every control has to stay inside the card, not be clipped by it.

    The bar is one horizontal row, so a field that is a few cells too wide
    silently pushes Filter/Clear past the right border — the buttons are still
    in the tree and still "clickable" for a flat assertion, they are just not
    drawn. The guard renders the bar at the width the app is used at and
    compares the right edge of the last control with the content area inside
    the card border.
    """
    result = await _clipped_controls(bar, 120)
    assert not result["clipped"], f"at 120 columns these controls are clipped: {result}"


@pytest.mark.asyncio
@pytest.mark.parametrize("bar", [ProxyFilterBar, WsFilterBar], ids=lambda c: c.__name__)
@pytest.mark.parametrize("width", [100, 90])
async def test_bar_controls_fit_after_shrinking_the_terminal(bar: type[HistoryFilterBar], width: int) -> None:
    """Shrinking the terminal must not cut the controls off.

    A single row cannot hold five labelled fields plus two spelled-out toggles
    and Filter/Clear below ~113 cells (measured), so the bar stacks its two
    logical rows instead of abbreviating anything. This is the case the user hit
    while reviewing the cards UI: Filter/Clear were cut off at 100 and 90.
    """
    result = await _clipped_controls(bar, width, shrink=True)
    assert not result["clipped"], f"bar clipped at {width} columns: {result}"


@pytest.mark.asyncio
async def test_narrow_bar_stacks_its_rows() -> None:
    """Two rows, but nothing abbreviated: the words stay."""
    result = await _clipped_controls(ProxyFilterBar, 90, shrink=True)
    assert result["two_rows"] is True
    assert result["scope_label"] == "Scope"
    assert result["comments_label"] == "Comments"
    assert result["apply_label"] == "Filter"
    assert result["reset_label"] == "Clear"


@pytest.mark.asyncio
async def test_wide_bar_keeps_a_single_row() -> None:
    """At 120 columns the two rows sit side by side again."""
    result = await _clipped_controls(ProxyFilterBar, 120)
    assert result["two_rows"] is False
    assert result["scope_label"] == "Scope"
    assert result["apply_label"] == "Filter"


@pytest.mark.asyncio
async def test_toggle_label_spells_the_state_it_is_in() -> None:
    """Clicking a toggle rewrites its label — that is why words cost only one word.

    `Scope` → `In scope`, `Comments` → `Commented`: the button always reads like
    the filter it applies, so the glyph-and-tooltip trick is not needed.
    """

    class _Host(App):
        CSS = (
            _APP_CSS
            + """
        #table-area { height: 1fr; width: 1fr; }
        #filter-bar { height: auto; }
        """
        )

        def compose(self):
            with Vertical(id="table-area"):
                yield ProxyFilterBar(id="filter-bar", classes="card")

    app = _Host()
    async with app.run_test(size=(120, 20)) as pilot:
        await pilot.pause()
        bar = app.query_one("#filter-bar", ProxyFilterBar)
        await pilot.click("#fb-scope")
        await pilot.click("#fb-comments")
        await pilot.pause()
        scope = str(bar.query_one("#fb-scope", ToolbarButton).label)
        comments = str(bar.query_one("#fb-comments", ToolbarButton).label)
        predicates = {p.field for p in bar.collect()}
    assert scope == "In scope"
    assert comments == "Commented"
    assert {"scope_only", "comment"} <= predicates


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
