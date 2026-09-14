"""Unit tests for pentool/tui/widgets/payload_drop_zone.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pentool.tui.widgets.payload_drop_zone import PayloadDropZone


def _make_zone() -> PayloadDropZone:
    with patch("textual.widget.Widget.__init__", return_value=None):
        z = PayloadDropZone.__new__(PayloadDropZone)
    z._classes = set()
    return z


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            z = PayloadDropZone.__new__(PayloadDropZone)
        assert len(z.DEFAULT_CSS) > 0

    def test_init_calls_update_text(self) -> None:
        """__init__ calls update_text()."""
        updated = []
        with patch("textual.widget.Widget.__init__", return_value=None):
            z = PayloadDropZone.__new__(PayloadDropZone)

        def fake_update(count: int = 0) -> None:
            updated.append(count)

        z.update_text = fake_update  # type: ignore[method-assign]
        PayloadDropZone.__init__(z)
        assert len(updated) == 1


class TestRender:
    def test_render_returns_hint_text(self) -> None:
        z = _make_zone()
        text = z.render()
        assert "Drop" in text
        assert "txt" in text or ".txt" in text
        assert "yaml" in text


class TestUpdateText:
    def test_update_text_accepts_count(self) -> None:
        """update_text handles a count argument without error."""
        z = _make_zone()
        z.update_text(42)
        z.update_text()

    def test_update_text_is_noop(self) -> None:
        z = _make_zone()
        z.update_text()  # noop by design


class TestPayloadsLoaded:
    def test_message_has_payloads(self) -> None:
        msg = PayloadDropZone.PayloadsLoaded(["a", "b"], source_path="/tmp/test.txt")
        assert msg.payloads == ["a", "b"]
        assert msg.source_path == "/tmp/test.txt"

    def test_message_default_source_path(self) -> None:
        msg = PayloadDropZone.PayloadsLoaded(["x"])
        assert msg.payloads == ["x"]
        assert msg.source_path == ""


class TestLoadFromPath:
    def test_load_from_path_calls_api(self) -> None:
        z = _make_zone()

        with patch("pentool.api.intruder_api.load_payloads_from_file", return_value=["p1", "p2"]), \
             patch.object(PayloadDropZone, "post_message") as pm:
            z.load_from_path("/fake/file.txt")

        pm.assert_called_once()
        msg = pm.call_args[0][0]
        assert isinstance(msg, PayloadDropZone.PayloadsLoaded)
        assert msg.payloads == ["p1", "p2"]
        assert msg.source_path == "/fake/file.txt"

    def test_load_from_path_empty_payloads_no_message(self) -> None:
        z = _make_zone()

        with patch("pentool.api.intruder_api.load_payloads_from_file", return_value=[]), \
             patch.object(PayloadDropZone, "post_message") as pm:
            z.load_from_path("/fake/empty.txt")

        pm.assert_not_called()


class TestOnClick:
    def test_on_click_opens_dialog(self) -> None:
        z = _make_zone()
        mock_app = MagicMock()

        with patch("pentool.tui.dialogs.file_selector.FileSelectorDialog"), \
             patch("textual.widget.Widget.app", new=mock_app, create=True):
            z.on_click()

        mock_app.push_screen.assert_called_once()

    def test_on_click_handles_exception(self) -> None:
        z = _make_zone()
        mock_app = MagicMock()
        mock_app.push_screen.side_effect = RuntimeError("boom")

        with patch("pentool.tui.dialogs.file_selector.FileSelectorDialog"), \
             patch("textual.widget.Widget.app", new=mock_app, create=True):
            z.on_click()