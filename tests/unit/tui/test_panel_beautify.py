"""Beautify works from the panel, not from the module header.

Owner's finding: the ✨ tool exists in the request/response windows, so a header button is a
duplicate. The panel tool posted `FormatToggleRequested` that only the Decoder answered (with
a no-op), so removing the header button without wiring the panel would have removed the
feature. Both halves are pinned here.
"""

from __future__ import annotations

from types import SimpleNamespace

from pentool.tui.screens.module_screen import ModuleScreen


class _Panel:
    def __init__(self, widget) -> None:
        self.content_widget = widget


class _Widget:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls = 0

    def beautify_body(self) -> bool:
        self.calls += 1
        return self.result


def test_header_no_longer_offers_beautify() -> None:
    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.tui.screens.repeater.screen import RepeaterScreen

    for cls in (IntruderScreen, RepeaterScreen):
        spec = cls().header_spec()
        labels = [action.label for action in (*spec.actions, *spec.more, *spec.state)]
        assert not any("Beautify" in label for label in labels), f"{cls.__name__}: beautify остался в шапке"


def test_panel_format_request_beautifies_the_body() -> None:
    screen = ModuleScreen.__new__(ModuleScreen)  # no DOM needed: handler is self-contained
    notes: list[tuple[str, str]] = []
    screen.notify_user = lambda message, severity="information", **_: notes.append((message, severity))

    widget = _Widget(result=True)
    screen.on_panel_format_requested(SimpleNamespace(panel=_Panel(widget)))

    assert widget.calls == 1, "нажатие ✨ в панели должно вызывать beautify_body()"
    assert notes and notes[0][1] == "information"


def test_panel_format_request_reports_nothing_to_change() -> None:
    screen = ModuleScreen.__new__(ModuleScreen)
    notes: list[tuple[str, str]] = []
    screen.notify_user = lambda message, severity="information", **_: notes.append((message, severity))

    widget = _Widget(result=False)
    screen.on_panel_format_requested(SimpleNamespace(panel=_Panel(widget)))

    assert widget.calls == 1
    assert notes and notes[0][1] == "warning", "если форматировать нечего — предупредить, а не молчать"
