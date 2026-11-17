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
    """PRO scanner screen — skip if not available (no pro/ submodule)."""
    import sys

    try:
        sys.path.insert(0, "pro")
        from pentool.tui.screens.scanner.screen import ScannerScreen

        assert ScannerScreen is not None
    except ModuleNotFoundError:
        pytest.skip("PRO package not available (no pro/ submodule)")


def test_import_search_bar():
    from pentool.tui.widgets.search_bar import SearchBar

    assert SearchBar is not None


def test_import_request_editor():
    from pentool.tui.widgets.request_editor import HttpView, RequestEditor, ResponseViewer

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
    import sys

    from pentool.tui.screens.intruder.screen import IntruderScreen
    from pentool.tui.screens.proxy.screen import ProxyScreen
    from pentool.tui.screens.repeater.screen import RepeaterScreen

    sys.path.insert(0, "pro")
    import inspect

    classes = [RepeaterScreen, IntruderScreen, ProxyScreen]
    try:
        from pentool.tui.screens.scanner.screen import ScannerScreen

        classes.append(ScannerScreen)
    except ModuleNotFoundError:
        pass
    for cls in classes:
        if hasattr(cls, "compose"):
            src = inspect.getsource(cls.compose)
            src = "\n".join(line[4:] if line.startswith("    ") else line for line in src.splitlines())
            compile(src, f"{cls.__name__}.compose", "exec")


def test_bindings():
    """Check BINDINGS validity for all module screens.

    Every binding must reference an existing action_* method.
    Single-letter bindings (showing in footer) must have priority=True
    so they work inside TabbedContent/DataTable focus.
    """
    import sys

    sys.path.insert(0, "pro")

    # (name, class) pairs for every module screen
    _screen_classes: list[tuple[str, type]] = []

    from pentool.tui.screens.proxy.screen import ProxyScreen

    _screen_classes.append(("ProxyScreen", ProxyScreen))
    from pentool.tui.screens.repeater.screen import RepeaterScreen

    _screen_classes.append(("RepeaterScreen", RepeaterScreen))
    from pentool.tui.screens.intruder.screen import IntruderScreen

    _screen_classes.append(("IntruderScreen", IntruderScreen))
    from pentool.tui.screens.target.screen import TargetScreen

    _screen_classes.append(("TargetScreen", TargetScreen))
    from pentool.tui.screens.dashboard.screen import DashboardScreen

    _screen_classes.append(("DashboardScreen", DashboardScreen))
    from pentool.tui.screens.decoder.screen import DecoderScreen

    _screen_classes.append(("DecoderScreen", DecoderScreen))
    from pentool.tui.screens.comparer.screen import ComparerScreen

    _screen_classes.append(("ComparerScreen", ComparerScreen))
    from pentool.tui.screens.sequencer.screen import SequencerScreen

    _screen_classes.append(("SequencerScreen", SequencerScreen))
    try:
        from pentool.tui.screens.scanner.screen import ScannerScreen

        _screen_classes.append(("ScannerScreen", ScannerScreen))
    except ModuleNotFoundError:
        pass

    def _single_key(key: str) -> bool:
        """A plain letter — the keys TabbedContent and DataTable try to eat."""
        return len(key) == 1 and key.isalpha()

    for name, cls in _screen_classes:
        if not hasattr(cls, "BINDINGS"):
            continue
        bindings = cls.BINDINGS

        for b in bindings:
            action_name = f"action_{b.action}"

            # 1) action_* method must exist
            if not hasattr(cls, action_name):
                pytest.fail(f"{name} binding '{b.key}' -> '{b.action}' but no {action_name} method")

            # 2) Single-letter show=True keys must have priority=True
            #    (prevents TabbedContent from eating them)
            if b.show and _single_key(b.key) and not b.priority:
                pytest.fail(
                    f"{name} single-letter binding '{b.key}' -> '{b.action}' "
                    f"has show=True but no priority=True — "
                    f"won't work inside DataTable focus"
                )

        # 3) Two bindings may not share BOTH the key and the action — that is a
        #    copy-paste, and the second copy can never fire. The same action on
        #    different keys is the opposite: it is how "Send" stays reachable
        #    from terminals with and without the Kitty keyboard protocol, so it
        #    is not reported at all. This used to warn on every multi-key action
        #    ("send" ×4, "focus_tab_history" ×2), which buried the one real
        #    duplicate — a hidden "O" twin of every open_in_browser binding
        #    (F-033).
        from collections import Counter

        pairs = Counter((b.key, b.action) for b in bindings)
        duplicated = {pair: n for pair, n in pairs.items() if n > 1}
        if duplicated:
            pytest.fail(
                f"{name} binds the same key to the same action more than once — the second copy is dead: {duplicated}"
            )

        shown = Counter(b.key for b in bindings if b.show)
        clashing = {key: n for key, n in shown.items() if n > 1}
        if clashing:
            pytest.fail(
                f"{name} shows the same key twice in the footer — one of the two bindings is unreachable: {clashing}"
            )
