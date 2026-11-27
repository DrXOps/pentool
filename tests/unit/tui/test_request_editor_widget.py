"""HTTP editor widgets: text loading, special characters, beautify, response label (T-014).

`request_editor.py` is the surface Proxy/Repeater show requests and responses in. The pure
helpers were covered; the widget methods were not — exactly the pатhs where "the request
arrived but the panel shows the previous one" lived. These tests mount the real widgets
(HttpView / RequestEditor / ResponseViewer) in a small app.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea

from pentool.tui.widgets.request_editor import (
    HttpView,
    RequestEditor,
    ResponseViewer,
    _build_body_highlights,
    _select_word_at_cursor,
)
from pentool.utils.parser import ParsedRequest, ParsedResponse

REQUEST = "GET /a HTTP/1.1\r\nHost: example.com\r\n\r\n"
JSON_REQUEST = 'POST /api HTTP/1.1\r\nHost: example.com\r\nContent-Type: application/json\r\n\r\n{"a": 1}'


class _EditorApp(App):
    def compose(self) -> ComposeResult:
        yield HttpView(title="View", id="view")
        yield RequestEditor(label="Request", id="req")
        yield ResponseViewer(id="resp")


@pytest.fixture
async def editor_app():
    app = _EditorApp()
    async with app.run_test(size=(160, 45)) as pilot:
        yield app, pilot


def _area(widget) -> TextArea:
    return widget.query_one("#cp-body-widget", TextArea)


# ── HttpView ───────────────────────────────────────────────────────────────


class TestHttpView:
    async def test_load_raw_http_shows_the_text(self, editor_app) -> None:
        app, _pilot = editor_app
        view = app.query_one("#view", HttpView)
        view.load_raw_http("HTTP/1.1 200 OK\nContent-Type: text/plain\n\nhello")
        assert "200 OK" in _area(view).text
        assert "hello" in _area(view).text

    async def test_empty_text_clears_the_panel(self, editor_app) -> None:
        app, _pilot = editor_app
        view = app.query_one("#view", HttpView)
        view.load_raw_http("HTTP/1.1 200 OK\n\nbody")
        view.load_raw_http("   ")
        assert _area(view).text == ""


# ── RequestEditor ──────────────────────────────────────────────────────────


class TestRequestEditorLoading:
    async def test_load_raw_fills_the_editor_and_keeps_the_headers(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw(REQUEST)

        assert "GET /a" in _area(editor).text
        assert editor._raw_full == REQUEST
        assert editor._headers_part.startswith("GET /a")

    async def test_load_raw_without_body_keeps_everything_in_headers(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw("GET /only-headers HTTP/1.1")
        assert editor._headers_part == "GET /only-headers HTTP/1.1"

    async def test_load_request_builds_raw_from_parsed(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_request(ParsedRequest(method="PUT", url="http://example.com/item", headers={"Host": "example.com"}))
        assert "PUT /item HTTP/1.1" in _area(editor).text

    async def test_clear_empties_text_and_flags(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw(REQUEST)
        editor.clear()
        assert _area(editor).text == ""
        assert editor._raw_full == ""
        assert editor._headers_part == ""
        assert editor._special_chars_mode is False


class TestRequestEditorSpecialChars:
    async def test_toggle_shows_and_hides_control_characters(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw(REQUEST)

        button = SimpleNamespace(label="", add_class=lambda _c: None, remove_class=lambda _c: None)
        editor._on_special_chars(SimpleNamespace(button=button))

        shown = _area(editor).text
        assert "\\r\\n" in shown, "перевод строки должен быть показан как \\r\\n"
        assert editor.get_text() == REQUEST, "get_text() возвращает исходный текст, а не визуализированный"

        editor._on_special_chars(SimpleNamespace(button=button))
        # The decoder restores real CR/LF: the editor holds the original request again.
        assert editor.get_text() == REQUEST
        assert "\\r\\n" not in _area(editor).text

    async def test_decode_special_chars_static(self) -> None:
        assert RequestEditor._decode_special_chars("a\\r\\n\nb") == "a\r\nb"


class TestRequestEditorBeautify:
    async def test_json_body_is_pretty_printed(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw(JSON_REQUEST)

        assert editor.beautify_body() is True
        text = _area(editor).text
        assert '  "a": 1' in text, "тело JSON должно быть отформатировано с отступом"

    async def test_no_body_is_not_beautified(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw(REQUEST)
        assert editor.beautify_body() is False

    async def test_unknown_body_is_not_beautified(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw("POST / HTTP/1.1\n\nplain text body")
        assert editor.beautify_body() is False

    async def test_xml_body_is_pretty_printed(self, editor_app) -> None:
        app, _pilot = editor_app
        editor = app.query_one("#req", RequestEditor)
        editor.load_raw("POST / HTTP/1.1\n\n<a><b>1</b></a>")
        assert editor.beautify_body() is True
        assert "\n  <b>" in _area(editor).text


# ── ResponseViewer ─────────────────────────────────────────────────────────


class TestResponseViewer:
    async def test_load_response_shows_status_headers_and_body(self, editor_app) -> None:
        app, _pilot = editor_app
        viewer = app.query_one("#resp", ResponseViewer)
        viewer.load_response(
            ParsedResponse(status=200, reason="OK", headers={"Content-Type": "application/json"}, body='{"ok": true}')
        )
        text = _area(viewer).text
        assert "HTTP/1.1 200 OK" in text
        assert "Content-Type: application/json" in text
        assert '"ok": true' in text

    async def test_label_carries_status_and_size(self, editor_app) -> None:
        app, _pilot = editor_app
        viewer = app.query_one("#resp", ResponseViewer)
        viewer.load_response(ParsedResponse(status=404, reason="Not Found", headers={}, body="x" * 2048))
        title = viewer._panel_title
        assert "404" in title and "2 KB" in title

    async def test_load_raw_and_clear_reset_the_label(self, editor_app) -> None:
        app, _pilot = editor_app
        viewer = app.query_one("#resp", ResponseViewer)
        viewer.load_response(ParsedResponse(status=200, reason="OK", headers={}, body="body"))
        viewer.load_raw("HTTP/1.1 500 Internal Server Error\n\nboom")
        assert "500" in _area(viewer).text
        viewer.clear()
        assert _area(viewer).text == ""

    async def test_beautify_response_body(self, editor_app) -> None:
        app, _pilot = editor_app
        viewer = app.query_one("#resp", ResponseViewer)
        viewer.load_response(
            ParsedResponse(status=200, reason="OK", headers={"Content-Type": "application/json"}, body='{"a":[1,2]}')
        )
        assert viewer.beautify_body() is True
        assert '"a"' in _area(viewer).text


# ── pure helpers that had no tests ─────────────────────────────────────────


class TestBodyHighlights:
    def test_json_body_gets_highlights(self) -> None:
        hl = _build_body_highlights(['{"key": "value"}'], "json", 3)
        assert 3 in hl and hl[3]

    def test_html_body_gets_highlights(self) -> None:
        hl = _build_body_highlights(["<div class='x'>hi</div>"], "html", 1)
        assert 1 in hl and hl[1]

    def test_unknown_language_returns_empty(self) -> None:
        assert _build_body_highlights(["plain"], "python", 0) == {}


class TestWordSelection:
    def test_selects_the_word_under_the_cursor(self) -> None:
        area = TextArea("GET /api/user HTTP/1.1")
        area.selection = ((0, 6), (0, 6))  # cursor inside "api"
        _select_word_at_cursor(area)
        (start, end) = area.selection
        # "/" is a word character on purpose: a double-click on a URL selects the whole
        # path (/api/user), not just the last segment.
        assert start == (0, 4) and end == (0, 13), "двойной клик должен выделить путь /api/user"
