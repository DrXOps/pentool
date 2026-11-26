"""Target: the Site Map card must start at the top, not half a screen down.

Owner: the Site Map card frame was shifted half a screen down.

Cause: `TargetScreen` is a vertical layout with two children — `#tgt-config-row` (a row of
checkboxes) and `#main-split`. The row had no height rule, so it defaulted to `1fr` and ate
half the screen, pushing the Site Map card down. The row is now `height: auto`.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


@pytest.mark.asyncio
async def test_site_map_starts_directly_under_the_config_row() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    async with app.run_test(size=(160, 45)) as pilot:
        for _ in range(12):
            await pilot.pause()
        app.action_switch_module("target")
        for _ in range(30):
            await pilot.pause()

        config_row = app.query_one("#tgt-config-row")
        main_split = app.query_one("#main-split")

        assert config_row.size.height <= 2, f"the config row took {config_row.size.height} rows - it must stay thin"
        assert main_split.region.y <= 3, (
            f"the site map starts at row {main_split.region.y}: the config row pushed it down"
        )
