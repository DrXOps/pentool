async def test_pause_resume_button_label_toggles(self) -> None:
        """Regression: '#btn-start' label must switch between "▶ Start" and
        "⏸ Pause" / "▶ Resume" as action_toggle_pause() is called.
        """
        from unittest.mock import AsyncMock

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(IntruderScreen)
            btn = screen.query_one("#btn-start", ToolbarButton)

            # Initial state — not running
            assert btn.label == "▶ Start"

            # Simulate an attack in progress with a fake API (no real HTTP).
            screen._attack_running = True
            screen._api = AsyncMock()
            btn.label = "⏸ Pause"

            screen.action_toggle_pause()
            await pilot.pause()
            assert screen._paused is True
            assert btn.label == "▶ Resume"

            screen.action_toggle_pause()
            await pilot.pause()
            assert screen._paused is False
            assert btn.label == "⏸ Pause"

    async def test_stop_attack_resets_pause_label_even_when_paused(self) -> None:
        """Regression: stopping an attack while it's paused must reset
        '#btn-start' back to "▶ Start" — otherwise the NEXT Start Attack
        would show "▶ Resume" left over from the stopped run."""
        from unittest.mock import AsyncMock

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(IntruderScreen)
            btn = screen.query_one("#btn-start", ToolbarButton)

            screen._attack_running = True
            screen._api = AsyncMock()
            btn.label = "⏸ Pause"
            screen.action_toggle_pause()
            await pilot.pause()
            assert btn.label == "▶ Resume"

            screen.action_stop_attack()
            await pilot.pause()
            assert screen._attack_running is False
            assert screen._paused is False
            assert btn.label == "▶ Start"