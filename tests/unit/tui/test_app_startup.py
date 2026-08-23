"""Test that the app can start without crashing.

Imports all screens and verifies basic structure — no TUI event loop required.
Catches simple import-time / syntax / composition errors.
"""
import pytest


def test_import_app():
    """Import the app module."""
    from pentool.tui.app import PentoolApp
    assert PentoolApp is not None


def test_import_repeater():
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    assert RepeaterScreen is not None


def test_import_intruder():
    from pentool.tui.screens.intruder.screen import IntruderScreen
    assert IntruderScreen is not None


def test_import_proxy():
    from pentool.tui.screens.proxy.screen import ProxyScreen
    assert ProxyScreen is not None


def test_import_scanner():
    """PRO scanner screen (needs sys.path hack for pro/)."""
    import sys
    sys.path.insert(0, "pro")
    from pentool.tui.screens.scanner.screen import ScannerScreen
    assert ScannerScreen is not None


def test_import_search_bar():
    from pentool.tui.widgets.search_bar import SearchBar
    assert SearchBar is not None


def test_import_request_editor():
    from pentool.tui.widgets.request_editor import (
        RequestEditor, ResponseViewer, HttpView,
    )
    assert RequestEditor is not None
    assert ResponseViewer is not None
    assert HttpView is not None


def test_import_storage():
    from pentool.storage.http_storage import HttpStorage
    assert HttpStorage is not None


def test_import_proxy_service():
    from pentool.services.proxy_service import ProxyService
    assert ProxyService is not None


def test_compose_methods():
    """Check that all compose() methods parse correctly (no syntax errors)."""
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.tui.screens.proxy.screen import ProxyScreen
    import sys
    sys.path.insert(0, "pro")
    from pentool.tui.screens.scanner.screen import ScannerScreen
    import inspect, textwrap
    # Just check compose is valid Python
    for cls in (RepeaterScreen, IntruderScreen, ProxyScreen, ScannerScreen):
        if hasattr(cls, "compose"):
            src = inspect.getsource(cls.compose)
            src = "\n".join(line[4:] if line.startswith("    ") else line
                            for line in src.splitlines())
            compile(src, f"{cls.__name__}.compose", "exec")


def test_bindings():
    """Check BINDINGS don't reference non-existent action_* methods."""
    from pentool.tui.screens.repeater.screen import RepeaterScreen
    from pentool.tui.screens.intruder.screen import IntruderScreen
    import sys
    sys.path.insert(0, "pro")
    from pentool.tui.screens.scanner.screen import ScannerScreen

    for cls in (RepeaterScreen, ScannerScreen):
        if not hasattr(cls, "BINDINGS"):
            continue
        for b in cls.BINDINGS:
            action_name = f"action_{b.action}"
            if not hasattr(cls, action_name):
                pytest.fail(
                    f"{cls.__name__} binding '{b.key}' -> '{b.action}' "
                    f"but no {action_name} method"
                )
