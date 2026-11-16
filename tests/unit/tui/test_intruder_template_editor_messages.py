"""Intruder's template-editor handlers read the field the message actually has.

``TextArea.Changed`` and ``TextArea.SelectionChanged`` carry ``text_area``;
they have no ``widget`` attribute. Both Intruder handlers asked for
``event.widget``, so every keystroke and every selection in the template
editor raised ``AttributeError``. The handler body sat inside a
``except (LookupError, NoMatches)`` block, so the raise escaped to Textual's
dispatcher — but the two things the handlers exist for never happened:

* payload sets were not recomputed from the edited template, so the Payloads
  selector kept describing the request as it was loaded;
* the last selection was never remembered, so marking a selection with ``§§``
  had nothing to mark;
* the per-tab auto-save did not run on edits.

The exception is only visible because Textual's ``run_test`` re-raises what a
handler let through — the same reason these tests mount the real screen and
type into the real editor instead of calling the methods with a fake event.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.widgets import ContentSwitcher, TextArea
from textual.widgets.text_area import Selection

from pentool.tui.screens.intruder.screen import IntruderScreen


class _App(App):
    def compose(self) -> ComposeResult:
        with ContentSwitcher():
            yield IntruderScreen()


async def _mounted(pilot):
    """Wait for the active tab's template panel and return the screen + editor.

    The panel is mounted asynchronously (the tab is built when the pane is
    activated), so a single ``pause`` is not enough — the same screen mounted
    after another test's auto-save takes one or two frames longer.
    """
    await pilot.pause()
    screen = pilot.app.query_one(IntruderScreen)
    for _ in range(20):
        try:
            return screen, screen._template_editor().content_widget
        except (LookupError, NoMatches):
            await pilot.pause()
    raise AssertionError("Intruder template panel never mounted")


@pytest.mark.asyncio
async def test_typing_in_template_recomputes_payload_select() -> None:
    app = _App()
    async with app.run_test(size=(200, 60)) as pilot:
        screen, area = await _mounted(pilot)
        calls: list[int] = []
        screen._update_payload_select = lambda: calls.append(1)  # type: ignore[method-assign]

        area.insert("GET /probe HTTP/1.1\r\n")
        await pilot.pause()
        await pilot.pause()

    assert calls, "editing the template must recompute the payload selector"


@pytest.mark.asyncio
async def test_selecting_in_template_remembers_the_range() -> None:
    app = _App()
    async with app.run_test(size=(200, 60)) as pilot:
        screen, area = await _mounted(pilot)
        area.load_text("GET /a HTTP/1.1\r\nHost: a.example\r\n\r\n")
        area.selection = area.selection.__class__(start=(1, 0), end=(1, 4))
        await pilot.pause()
        await pilot.pause()

    remembered = screen._last_editor_selection
    assert remembered is not None, "selecting text in the template must be remembered for «mark selection»"


@pytest.mark.asyncio
async def test_events_from_another_editor_are_ignored() -> None:
    """The guards that make the handler tab-scoped must still hold.

    A response editor lives in the same screen; typing there must not touch
    Intruder's payload selector, otherwise every byte of a response would
    reset the user's payload choice. The message is built directly from a
    foreign ``TextArea`` and handed to the handler: mounting a second editor
    inside the screen makes Textual re-activate the tab and the template pane
    flaps, which is a property of the harness, not of the guard.
    """
    app = _App()
    async with app.run_test(size=(200, 60)) as pilot:
        screen, _area = await _mounted(pilot)
        calls: list[int] = []
        screen._update_payload_select = lambda: calls.append(1)  # type: ignore[method-assign]

        stray = TextArea("typing elsewhere")
        screen.on_template_text_changed(TextArea.Changed(stray))
        screen.on_template_selection_changed(TextArea.SelectionChanged(Selection.cursor((0, 0)), stray))
        await pilot.pause()

    assert not calls, "an editor outside the template panel must not recompute payloads"
