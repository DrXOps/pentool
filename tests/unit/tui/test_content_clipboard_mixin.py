"""Regression tests for ContentClipboardMixin handler dispatch.

The mixin used to declare its handlers with ``@on(...)``. Textual registers
``@on`` handlers only in the concrete class that defines them (it walks the
class ``__dict__``, not the MRO), so on a plain mixin the handlers were never
registered and every Copy/Paste button in the app silently did nothing.
See docs/audit/2026-11-21-tui-report.md, finding F-001.
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import TextArea

from pentool.tui.mixins.content_clipboard_mixin import ContentClipboardMixin
from pentool.tui.widgets.content_panel import ContentPanel


class _ClipboardHost(ContentClipboardMixin, App):
    """App that records what the mixin asked to paste and notify."""

    def __init__(self) -> None:
        super().__init__()
        self.pasted: list[str] = []
        self.notices: list[str] = []

    def _paste_text_to_panel(self, panel: ContentPanel, text: str) -> None:  # noqa: D401
        self.pasted.append(text)

    def notify_user(
        self,
        message: str,
        *,
        severity: str = "information",
        timeout: float | None = 3,
        title: str | None = None,
    ) -> None:
        """`NotifyMixin` surface — the mixin reports through it, not through app.notify."""
        self.notices.append(str(message))

    def notify(self, message, **kwargs) -> None:  # type: ignore[override]
        self.notices.append(str(message))


@pytest.fixture
def clipboard(monkeypatch: pytest.MonkeyPatch) -> dict[str, str | None]:
    state: dict[str, str | None] = {"text": "CLIP"}
    monkeypatch.setattr(
        "pentool.utils.copy_as.paste_from_clipboard",
        lambda: state["text"],
    )
    monkeypatch.setattr(
        "pentool.utils.copy_as.copy_to_clipboard",
        lambda text: True,
    )
    return state


class TestMixinDispatchesByConvention:
    async def test_paste_requested_reaches_mixin(self, clipboard) -> None:
        app = _ClipboardHost()
        async with app.run_test() as pilot:
            panel = ContentPanel("t", widget_type="richlog", id="cp")
            await app.mount(panel)
            await pilot.pause()

            panel.post_message(ContentPanel.PasteRequested(panel))
            await pilot.pause()

            assert app.pasted == ["CLIP"], (
                "ContentClipboardMixin must receive PasteRequested — an @on "
                "decorator in a plain mixin is not registered by Textual"
            )

    async def test_paste_with_empty_clipboard_warns_and_does_not_paste(self, clipboard) -> None:
        clipboard["text"] = None
        app = _ClipboardHost()
        async with app.run_test() as pilot:
            panel = ContentPanel("t", widget_type="richlog", id="cp")
            await app.mount(panel)
            await pilot.pause()

            panel.post_message(ContentPanel.PasteRequested(panel))
            await pilot.pause()

            assert app.pasted == []
            assert any("clipboard" in n.lower() for n in app.notices)

    async def test_copy_requested_reaches_mixin(self, clipboard) -> None:
        app = _ClipboardHost()
        async with app.run_test() as pilot:
            panel = ContentPanel("t", widget_type="richlog", id="cp")
            await app.mount(panel)
            await pilot.pause()

            panel.post_message(ContentPanel.CopyRequested(panel, "hello"))
            await pilot.pause()

            assert any("copied" in n.lower() for n in app.notices)

    def test_mixin_uses_no_on_decorators(self) -> None:
        """ADR-3: mixins must not use @on — it is not dispatched from the MRO."""
        for name in dir(ContentClipboardMixin):
            attr = getattr(ContentClipboardMixin, name)
            assert not getattr(attr, "_textual_on", None), (
                f"ContentClipboardMixin.{name} uses @on(); declare handlers by name instead (see ADR-3)"
            )


class TestPasteIntoTypedWidgets:
    async def test_paste_replaces_selection_in_textarea(self, clipboard) -> None:
        """Default _paste_text_to_panel replaces the active selection."""
        app = _ClipboardHost()
        paste = ContentClipboardMixin._paste_text_to_panel.__get__(app)
        app._paste_text_to_panel = paste  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            panel = ContentPanel("t", widget_type="textarea", id="cp")
            await app.mount(panel)
            await pilot.pause()

            area = panel.content_widget
            assert isinstance(area, TextArea)
            area.load_text("hello world")
            area.selection = ((0, 0), (0, 5))
            await pilot.pause()

            panel.post_message(ContentPanel.PasteRequested(panel))
            await pilot.pause()

            assert area.text == "CLIP world"

    async def test_paste_inserts_at_cursor_without_selection(self, clipboard) -> None:
        app = _ClipboardHost()
        paste = ContentClipboardMixin._paste_text_to_panel.__get__(app)
        app._paste_text_to_panel = paste  # type: ignore[method-assign]
        async with app.run_test() as pilot:
            panel = ContentPanel("t", widget_type="textarea", id="cp")
            await app.mount(panel)
            await pilot.pause()

            area = panel.content_widget
            assert isinstance(area, TextArea)
            area.load_text("ab")
            area.move_cursor((0, 2))
            area.selection = ((0, 2), (0, 2))
            await pilot.pause()

            panel.post_message(ContentPanel.PasteRequested(panel))
            await pilot.pause()

            assert area.text == "abCLIP"
