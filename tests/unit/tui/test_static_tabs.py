"""Static sub-tab factory: one shape and one memory for Utils/Settings/Recon (T-030)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from textual.widget import Widget

from pentool.core.config import Config
from pentool.tui.widgets.static_tabs import remember_tab, remembered_tab

TABS = (
    ("tabs-a", "A", lambda: Widget(id="body-a")),
    ("tabs-b", "B", lambda: Widget(id="body-b")),
)


def _config(remembered: dict[str, str] | None = None) -> Config:
    config = Config()
    config.last_subtabs = dict(remembered or {})
    return config


def test_remembered_tab_returns_saved_pane() -> None:
    with patch("pentool.core.config.get_config", return_value=_config({"utils": "tabs-b"})):
        assert remembered_tab(object(), "utils", TABS) == "tabs-b"


def test_remembered_tab_falls_back_to_first_pane() -> None:
    with patch("pentool.core.config.get_config", return_value=_config()):
        assert remembered_tab(object(), "utils", TABS) == "tabs-a"


def test_remembered_tab_ignores_unknown_pane() -> None:
    """A remembered id that no longer exists must not open an empty strip."""
    with patch("pentool.core.config.get_config", return_value=_config({"utils": "tabs-removed"})):
        assert remembered_tab(object(), "utils", TABS) == "tabs-a"


def test_remembered_tab_survives_broken_config() -> None:
    with patch("pentool.core.config.get_config", side_effect=RuntimeError("config unavailable")):
        assert remembered_tab(object(), "utils", TABS) == "tabs-a"


def test_remember_tab_writes_the_choice_once() -> None:
    config = _config()
    config.save = MagicMock()
    with patch("pentool.core.config.get_config", return_value=config):
        remember_tab(object(), "utils", "tabs-b")
        assert config.last_subtabs == {"utils": "tabs-b"}
        assert config.save.call_count == 1, "the first change is persisted"

        remember_tab(object(), "utils", "tabs-b")
        assert config.save.call_count == 1, "an unchanged pane must not rewrite the config"


def test_remember_tab_keeps_other_modules() -> None:
    config = _config({"settings": "settings-proxy"})
    config.save = MagicMock()
    with patch("pentool.core.config.get_config", return_value=config):
        remember_tab(object(), "utils", "tabs-b")
    assert config.last_subtabs == {"settings": "settings-proxy", "utils": "tabs-b"}


def test_remember_tab_never_raises() -> None:
    with patch("pentool.core.config.get_config", side_effect=RuntimeError("broken")):
        remember_tab(object(), "utils", "tabs-b")  # must not raise


def test_static_tabs_requires_at_least_one_pane() -> None:
    from pentool.tui.widgets.static_tabs import static_tabs

    with pytest.raises(ValueError):
        list(static_tabs("x", []))
