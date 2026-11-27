"""FilterBarWidget — every field type, ToggleButton, apply/reset (T-014).

The widget is the UI half of table filtering: `configure()` describes fields, `compose()`
renders them, `collect()` turns the controls back into `FilterPredicate`s and the bar posts
`FilterChanged` on Apply/Reset/Enter/cycler click. These tests pin that contract for all
five field types, including the paths that used to be untested (toggle, range, clearing and
the two "widget is gone" fallbacks).

An unticked toggle contributes nothing: "off" means "do not filter", not `field = False`.
"""

from __future__ import annotations

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label

from pentool.collections.filter_predicate import FilterField, FilterFieldType, FilterOp
from pentool.tui.widgets.filter_bar_widget import FilterBarWidget, ToggleButton
from pentool.tui.widgets.option_cycler import OptionCycler


class _AllFieldsBar(FilterBarWidget):
    def configure(self) -> list[FilterField]:
        return [
            FilterField("fb-host", "Host:", FilterFieldType.TEXT, "host", FilterOp.LIKE),
            FilterField("fb-status", "Status:", FilterFieldType.NUMBER, "status_code", FilterOp.EQ),
            FilterField(
                "fb-method",
                "Method:",
                FilterFieldType.CYCLER,
                "method",
                FilterOp.IN,
                options=[("Any", ""), ("GET", "GET"), ("POST", "POST")],
            ),
            FilterField("fb-errors", "Errors only", FilterFieldType.TOGGLE, "error_count", FilterOp.GT),
            FilterField("fb-length", "Length:", FilterFieldType.RANGE, "length", FilterOp.BETWEEN),
        ]


class _BarApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.specs: list[Any] = []

    def compose(self) -> ComposeResult:
        yield _AllFieldsBar(id="bar")

    def on_filter_bar_widget_filter_changed(self, event: FilterBarWidget.FilterChanged) -> None:
        self.specs.append(event.spec)

    @property
    def bar(self) -> _AllFieldsBar:
        return self.query_one(_AllFieldsBar)


@pytest.fixture
async def bar_app():
    app = _BarApp()
    async with app.run_test(size=(120, 30)) as pilot:
        yield app, pilot


# ── ToggleButton ───────────────────────────────────────────────────────────


class TestToggleButton:
    def test_starts_inactive_with_its_label(self) -> None:
        btn = ToggleButton("Errors only")
        assert btn.is_active() is False
        assert btn._label == "Errors only"
        assert btn._active_label == "Errors only"

    def test_toggle_flips_state_and_posts_the_new_value(self) -> None:
        btn = ToggleButton("Off", "On")
        posted: list[Any] = []
        btn.post_message = lambda msg: posted.append(msg)  # type: ignore[method-assign]

        btn.toggle()
        assert btn.is_active() is True
        assert "-active" in btn.classes
        assert len(posted) == 1 and posted[0].active is True

        btn.toggle()
        assert btn.is_active() is False
        assert posted[-1].active is False

    def test_click_toggles(self) -> None:
        btn = ToggleButton("X")
        btn.post_message = lambda msg: None  # type: ignore[method-assign]
        btn.on_click()
        assert btn.is_active() is True

    def test_reset_returns_to_the_initial_state(self) -> None:
        btn = ToggleButton("Off", "On")
        btn.post_message = lambda msg: None  # type: ignore[method-assign]
        btn.toggle()
        btn.reset()
        assert btn.is_active() is False
        assert "-active" not in btn.classes

    def test_set_enabled_marks_the_disabled_class(self) -> None:
        btn = ToggleButton("X")
        btn.set_enabled(False)
        assert "disabled" in btn.classes
        btn.set_enabled(True)
        assert "disabled" not in btn.classes


# ── Rendering ──────────────────────────────────────────────────────────────


class TestRendering:
    async def test_every_field_type_is_rendered(self, bar_app) -> None:
        app, _pilot = bar_app
        bar = app.bar
        assert isinstance(bar.query_one("#fb-host"), Input)
        assert isinstance(bar.query_one("#fb-status"), Input)
        assert isinstance(bar.query_one("#fb-method"), OptionCycler)
        assert isinstance(bar.query_one("#fb-errors"), ToggleButton)
        assert isinstance(bar.query_one("#fb-length-lo"), Input)
        assert isinstance(bar.query_one("#fb-length-hi"), Input)
        assert isinstance(bar.query_one("#fb-apply"), Button)
        assert isinstance(bar.query_one("#fb-reset"), Button)

    def test_range_renders_two_inputs_and_an_arrow(self) -> None:
        bar = object.__new__(FilterBarWidget)
        field = FilterField("r", "Len", FilterFieldType.RANGE, "length", FilterOp.BETWEEN)
        widgets = list(bar._render_field(field))
        assert [type(w).__name__ for w in widgets] == ["Input", "Label", "Input"]
        assert isinstance(widgets[1], Label)
        assert widgets[0].id == "r-lo" and widgets[2].id == "r-hi"


# ── collect(): values → predicates ─────────────────────────────────────────


class TestCollect:
    async def test_empty_bar_collects_nothing(self, bar_app) -> None:
        app, _pilot = bar_app
        assert app.bar.collect() == []

    async def test_all_field_types_collect_and_numbers_are_normalized(self, bar_app) -> None:
        app, _pilot = bar_app
        bar = app.bar
        bar.query_one("#fb-host", Input).value = "example.com"
        bar.query_one("#fb-status", Input).value = "404"
        bar.query_one("#fb-method", OptionCycler).on_click()
        bar.query_one("#fb-errors", ToggleButton).toggle()
        bar.query_one("#fb-length-lo", Input).value = "100"
        bar.query_one("#fb-length-hi", Input).value = "200"

        predicates = {p.field: p for p in bar.collect()}

        assert predicates["host"].value == "example.com"
        assert predicates["status_code"].value == 404, "номер должен стать int для SQL"
        assert predicates["method"].value == "GET"
        assert predicates["error_count"].value is True
        assert predicates["length"].value == (100, 200)

    async def test_unticked_toggle_does_not_filter(self, bar_app) -> None:
        app, _pilot = bar_app
        bar = app.bar
        bar.query_one("#fb-errors", ToggleButton).toggle()
        bar.query_one("#fb-errors", ToggleButton).toggle()  # back to off
        assert [p for p in bar.collect() if p.field == "error_count"] == []

    async def test_range_with_only_low_bound_collects_the_low_value(self, bar_app) -> None:
        app, _pilot = bar_app
        bar = app.bar
        bar.query_one("#fb-length-lo", Input).value = "500"
        predicate = bar.collect()[0]
        assert predicate.value == "500"
        assert predicate.operator is FilterOp.BETWEEN

    def test_non_numeric_values_survive_normalization(self) -> None:
        number = FilterField("n", "N", FilterFieldType.NUMBER, "n", FilterOp.EQ)
        rng = FilterField("r", "R", FilterFieldType.RANGE, "r", FilterOp.BETWEEN)
        assert FilterBarWidget._normalize_value(number, "abc") == "abc"
        assert FilterBarWidget._normalize_value(rng, ("1", "x")) == ("1", "x")
        assert FilterBarWidget._normalize_value(rng, "5") == "5"

    def test_missing_widget_reads_as_none(self) -> None:
        bar = object.__new__(FilterBarWidget)
        field = FilterField("gone", "G", FilterFieldType.TEXT, "g", FilterOp.LIKE)
        assert bar._read_field(field) is None


# ── apply / reset / handlers ───────────────────────────────────────────────


class TestApplyReset:
    async def test_apply_button_posts_the_spec(self, bar_app) -> None:
        app, pilot = bar_app
        app.bar.query_one("#fb-host", Input).value = "a.example"
        app.bar.query_one("#fb-apply", Button).press()
        await pilot.pause()
        assert app.specs, "нажатие Filter должно отправить FilterChanged"
        assert app.specs[-1].predicates[0].value == "a.example"

    async def test_reset_clears_fields_and_posts_an_empty_spec(self, bar_app) -> None:
        app, pilot = bar_app
        bar = app.bar
        bar.query_one("#fb-host", Input).value = "x"
        bar.query_one("#fb-status", Input).value = "200"
        bar.query_one("#fb-errors", ToggleButton).toggle()
        bar.query_one("#fb-method", OptionCycler).on_click()

        bar.query_one("#fb-reset", Button).press()
        await pilot.pause()

        assert app.specs[-1].predicates == []
        assert bar.query_one("#fb-host", Input).value == ""
        assert bar.query_one("#fb-status", Input).value == ""
        assert bar.query_one("#fb-errors", ToggleButton).is_active() is False
        assert bar.query_one("#fb-method", OptionCycler).value == ""

    async def test_enter_in_an_input_applies(self, bar_app) -> None:
        app, pilot = bar_app
        field = app.bar.query_one("#fb-host", Input)
        field.value = "enter.example"
        field.post_message(Input.Submitted(field, "enter.example"))
        await pilot.pause()
        assert app.specs and app.specs[-1].predicates[0].value == "enter.example"

    async def test_cycler_click_applies_immediately(self, bar_app) -> None:
        app, pilot = bar_app
        app.bar.query_one("#fb-method", OptionCycler).on_click()
        await pilot.pause()
        assert app.specs, "клик по циклеру должен применять фильтр без отдельной кнопки"
        assert app.specs[-1].predicates[0].value == "GET"

    def test_clear_of_a_missing_widget_is_logged_not_raised(self) -> None:
        bar = object.__new__(FilterBarWidget)
        field = FilterField("gone", "G", FilterFieldType.TEXT, "g", FilterOp.LIKE)
        bar._clear_field(field)  # no exception even though the widget is absent
