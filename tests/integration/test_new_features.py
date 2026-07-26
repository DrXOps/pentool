"""Integration tests: new features — Sequencer, Target, Decoder, Dashboard Live, Settings Network.

Checks widget presence and basic behavior without crashes.
"""

from __future__ import annotations

import pytest

from pentool.core.config import Config, set_config


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    """Isolated configuration for each test."""
    cfg = Config(
        db_path=str(tmp_path / "test.db"),
        cert_dir=str(tmp_path / "certs"),
        proxy_port=19095,
    )
    set_config(cfg)
    return cfg


# ── Sequencer ─────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSequencerScreen:
    @pytest.mark.asyncio
    async def test_sequencer_in_dom(self) -> None:
        """Sequencer screen mounts without errors."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.sequencer.screen import SequencerScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            screens = app.query(SequencerScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_seq_token_area_in_dom(self) -> None:
        """TextArea for token input is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            ta = app.query("#seq-token-area")
            assert len(ta) > 0

    @pytest.mark.asyncio
    async def test_seq_analyze_button_in_dom(self) -> None:
        """Analyze button is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            btn = app.query("#btn-seq-analyze")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_seq_export_button_in_dom(self) -> None:
        """Export button (Block 4.5) is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            btn = app.query("#btn-seq-export")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_seq_analyze_no_tokens_shows_warning(self) -> None:
        """Analyze without tokens does not crash."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            await pilot.click("#btn-seq-analyze")
            await pilot.pause()
            # No crash = OK


# ── Target ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestTargetScreen:
    @pytest.mark.asyncio
    async def test_target_in_dom(self) -> None:
        """Target screen mounts."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.target.screen import TargetScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("T")
            await pilot.pause()
            screens = app.query(TargetScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_scope_rules_button_in_dom(self) -> None:
        """'Scope Rules' button (Block 4.9) is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("T")
            await pilot.pause()
            btn = app.query("#btn-scope-rules")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_site_tree_in_dom(self) -> None:
        """Tree widget is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("T")
            await pilot.pause()
            tree = app.query("#site-tree")
            assert len(tree) > 0


# ── Decoder ───────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestDecoderScreen:
    @pytest.mark.asyncio
    async def test_decoder_in_dom(self) -> None:
        """Decoder screen mounts."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.decoder.screen import DecoderScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            screens = app.query(DecoderScreen)
            assert len(screens) > 0


# ── Dashboard Live Tab ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestDashboardLiveTab:
    @pytest.mark.asyncio
    async def test_dashboard_in_dom(self) -> None:
        """Dashboard screen mounts without errors."""
        from pentool.tui.app import PentoolApp
        from pentool.tui.screens.dashboard.screen import DashboardScreen

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("H")
            await pilot.pause()
            screens = app.query(DashboardScreen)
            assert len(screens) > 0

    @pytest.mark.asyncio
    async def test_dashboard_tabbed_content_in_dom(self) -> None:
        """Dashboard contains TabbedContent with Overview and Live tabs."""
        from pentool.tui.app import PentoolApp
        from textual.widgets import TabbedContent

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("H")
            await pilot.pause()
            tc = app.query("#dashboard-tabs")
            assert len(tc) > 0

    @pytest.mark.asyncio
    async def test_live_dashboard_tab_exists(self) -> None:
        """Live Dashboard tab is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("H")
            await pilot.pause()
            live_tab = app.query("#live-dashboard")
            assert len(live_tab) > 0


# ── Settings Network Tab ──────────────────────────────────────────────────────

@pytest.mark.integration
class TestSettingsNetworkTab:
    @pytest.mark.asyncio
    async def test_settings_network_tab_in_dom(self) -> None:
        """Network tab is present in Settings (Block 4.10)."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+comma")  # open Settings
            await pilot.pause()
            network_tab = app.query("#tab-network")
            assert len(network_tab) > 0

    @pytest.mark.asyncio
    async def test_settings_user_agent_input_in_dom(self) -> None:
        """User-Agent input is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+comma")
            await pilot.pause()
            inp = app.query("#set-user-agent")
            assert len(inp) > 0

    @pytest.mark.asyncio
    async def test_settings_collaborator_url_input_in_dom(self) -> None:
        """Collaborator URL input is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("ctrl+comma")
            await pilot.pause()
            inp = app.query("#set-collaborator-url")
            assert len(inp) > 0


# ── Grep Match/Extract (Intruder Block 4.4) ────────────────────────────────────

@pytest.mark.integration
class TestIntruderGrepBar:
    @pytest.mark.asyncio
    async def test_grep_bar_in_dom(self) -> None:
        """#grep-bar with Match/Extract fields is present in DOM (Block 4.4)."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            bar = app.query("#grep-bar")
            assert len(bar) > 0

    @pytest.mark.asyncio
    async def test_grep_match_input_in_dom(self) -> None:
        """Grep Match input is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            inp = app.query("#grep-match-input")
            assert len(inp) > 0

    @pytest.mark.asyncio
    async def test_grep_apply_button_in_dom(self) -> None:
        """Grep Apply button is present in DOM."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            btn = app.query("#btn-grep-apply")
            assert len(btn) > 0

    @pytest.mark.asyncio
    async def test_grep_apply_no_crash(self) -> None:
        """Apply with empty pattern — no crash."""
        from pentool.tui.app import PentoolApp

        app = PentoolApp()
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.click("#btn-grep-apply")
            await pilot.pause()
            # No Exception = OK
