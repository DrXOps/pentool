"""E2E: DecoderScreen — widgets present."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.decoder.screen import DecoderScreen


@pytest.mark.e2e
class TestDecoderScreen:

    async def test_decoder_screen_mounts(self) -> None:
        """press D → DecoderScreen присутствует в DOM."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            await pilot.pause()
            screens = app.query(DecoderScreen)
            assert len(screens) > 0

    async def test_input_area_present(self) -> None:
        """TextArea #dec-input присутствует в DecoderScreen."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            await pilot.pause()
            # DecoderScreen содержит TextArea с id="dec-input"
            input_area = app.query("#dec-input")
            assert len(input_area) > 0
