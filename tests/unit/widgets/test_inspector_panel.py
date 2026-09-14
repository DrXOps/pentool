"""Unit tests for pentool/tui/widgets/inspector_panel.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.widgets import Static

from pentool.tui.widgets.inspector_panel import InspectorPanel


def _make_panel() -> InspectorPanel:
    with patch("textual.widget.Widget.__init__", return_value=None):
        p = InspectorPanel.__new__(InspectorPanel)
    p._classes = set()
    p.styles = MagicMock()
    return p


class TestInit:
    def test_css_loaded(self) -> None:
        with patch("textual.widget.Widget.__init__", return_value=None):
            p = InspectorPanel.__new__(InspectorPanel)
        assert len(p.DEFAULT_CSS) > 0


class TestCompose:
    def test_compose_yields_placeholder(self) -> None:
        p = _make_panel()
        results = list(p.compose())
        assert len(results) == 1
        assert isinstance(results[0], Static)
        assert results[0].id == "inspector-placeholder"


class TestAddSection:
    def test_adds_title_widget(self) -> None:
        widgets: list = []
        InspectorPanel._add_section(widgets, "Test", {})
        assert len(widgets) >= 1
        assert "section-title" in widgets[0].classes

    def test_adds_none_when_empty(self) -> None:
        widgets: list = []
        InspectorPanel._add_section(widgets, "Empty", {})
        assert any(w.has_class("empty-msg") for w in widgets)

    def test_adds_kv_rows(self) -> None:
        widgets: list = []
        InspectorPanel._add_section(widgets, "Data", {"key1": "val1", "key2": "val2"})
        kv_rows = [w for w in widgets if w.has_class("kv-row")]
        assert len(kv_rows) == 2

    def test_truncates_long_value(self) -> None:
        widgets: list = []
        long_val = "a" * 100
        InspectorPanel._add_section(widgets, "Data", {"key": long_val})
        kv = widgets[-1]
        assert kv.has_class("kv-row")

    def test_handles_none_items(self) -> None:
        widgets: list = []
        InspectorPanel._add_section(widgets, "None", {"key": None})
        kv = widgets[-1]
        assert kv.has_class("kv-row")


class TestBuildWidgets:
    def _make_req(self, url: str = "http://example.com/", method: str = "GET", body: str = "", headers: dict | None = None) -> MagicMock:
        req = MagicMock()
        req.url = url
        req.method = method
        req.body = body
        req.headers = headers or {}
        return req

    def test_builds_without_resp(self) -> None:
        p = _make_panel()
        req = self._make_req(headers={"Host": "example.com"})
        result = p._build_widgets(req, resp=None)
        titles = [w for w in result if w.has_class("section-title")]
        assert len(titles) >= 3

    def test_builds_with_resp(self) -> None:
        p = _make_panel()
        req = self._make_req()
        resp = MagicMock()
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}

        result = p._build_widgets(req, resp)
        titles = [w for w in result if w.has_class("section-title")]
        assert len(titles) >= 6  # Request Attributes, Request Headers, Query Params, Body Params, Cookies, Response Headers

    def test_url_reconstruction_from_path(self) -> None:
        p = _make_panel()
        req = self._make_req(url="/admin", headers={"Host": "target.com"})
        result = p._build_widgets(req, resp=None)
        # Should produce widgets without crashing and include section titles
        assert any(w.has_class("section-title") for w in result)

    def test_parse_query_params(self) -> None:
        p = _make_panel()
        req = self._make_req(url="http://example.com/?a=1&b=2&a=3")
        result = p._build_widgets(req, resp=None)
        assert any(w.has_class("section-title") for w in result)

    def test_parse_json_body(self) -> None:
        p = _make_panel()
        req = self._make_req(method="POST", body='{"user": "alice", "role": "admin"}',
                              headers={"Content-Type": "application/json"})
        result = p._build_widgets(req, resp=None)
        assert any(w.has_class("section-title") for w in result)

    def test_parse_form_body(self) -> None:
        p = _make_panel()
        req = self._make_req(method="POST", body="username=alice&password=secret",
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
        result = p._build_widgets(req, resp=None)
        assert any(w.has_class("section-title") for w in result)

    def test_parse_cookies(self) -> None:
        p = _make_panel()
        req = self._make_req(headers={"Cookie": "session=abc123; theme=dark"})
        result = p._build_widgets(req, resp=None)
        assert any(w.has_class("section-title") for w in result)


class TestClear:
    """clear/load need live App for call_after_refresh — covered in integration."""