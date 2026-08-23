"""Smoke tests for the most recent changes:
- SearchBar: TargetToggle, toggle_target
- Repeater: ctrl+f via on_key, search in response
- Proxy: Show comments filter
- HttpStorage: has_comment in _build_where
- ResponseViewer: language=html/json/xml
- Repeater: cancel_node before switch_db
- Intruder: btn-pause removed
"""

import inspect
import sys

import pytest


@pytest.fixture(autouse=True)
def _pro_path():
    sys.path.insert(0, "pro")
    yield
    if "pro" in sys.path:
        sys.path.remove("pro")


def test_search_bar_target_toggle():
    from pentool.tui.widgets.search_bar import SearchBar
    assert hasattr(SearchBar, "TargetToggle"), "Missing TargetToggle message"
    assert hasattr(SearchBar, "toggle_target"), "Missing toggle_target method"


def test_repeater_on_key_ctrl_f():
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    src = inspect.getsource(RepeaterScreen.on_key)
    assert "ctrl+f" in src, "ctrl+f not handled in on_key"
    assert "action_toggle_search" in src, "toggle_search not called from on_key"


def test_repeater_get_active_text_search_target():
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    src = inspect.getsource(RepeaterScreen._get_active_text)
    assert "search_target" in src, "_get_active_text does not check search_target"
    assert "ResponseViewer" in src or "resp-viewer" in src, "no response viewer fallback"


def test_repeater_cancel_node_before_switch_db():
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    src = inspect.getsource(RepeaterScreen.reload_from_project)
    assert "cancel_node" in src, "missing cancel_node before switch_db"
    assert "switch_db" in src, "switch_db not called in reload_from_project"


def test_proxy_btn_show_comments():
    from pentool.tui.screens.proxy.screen import ProxyScreen
    src = inspect.getsource(ProxyScreen.on_btn_show_comments)
    assert "btn-show-comments" in src, "handler not for btn-show-comments"
    assert "_reset" in src, "does not reset filter bar"
    assert "run_worker" in src, "does not use run_worker"
    assert "_reload_table" in src, "does not call _reload_table"


def test_proxy_reload_table_has_comment():
    from pentool.tui.screens.proxy.screen import ProxyScreen
    src = inspect.getsource(ProxyScreen._reload_table)
    assert "_filter_show_comments" in src, "missing has_comment logic in _reload_table"


def test_http_storage_build_where_has_comment():
    from pentool.storage.http_storage import HttpStorage
    src = inspect.getsource(HttpStorage._build_where)
    assert "has_comment" in src, "has_comment not handled in _build_where"


def test_response_viewer_language():
    from pentool.tui.widgets.request_editor import ResponseViewer
    src = inspect.getsource(ResponseViewer.load_response)
    assert "area.language" in src, "language not set on TextArea for html/json/xml"


def test_intruder_btn_pause_removed():
    from pentool.tui.screens.intruder.screen import IntruderScreen
    src = inspect.getsource(IntruderScreen.compose)
    assert "btn-pause" not in src, "btn-pause still present in Intruder toolbar"
