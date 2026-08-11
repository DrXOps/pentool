"""E2E: IntruderScreen — load request, widgets."""
from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp
from pentool.tui.screens.intruder.screen import IntruderScreen
from pentool.utils.parser import ParsedRequest


@pytest.mark.e2e
class TestIntruderScreen:

    async def test_intruder_mounts(self) -> None:
        """press I → IntruderScreen присутствует в DOM."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            screens = app.query(IntruderScreen)
            assert len(screens) > 0

    async def test_start_button_present(self) -> None:
        """#btn-start присутствует в IntruderScreen."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            btn = app.query("#btn-start")
            assert len(btn) > 0

    async def test_template_editor_present(self) -> None:
        """#template-editor присутствует в IntruderScreen."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()
            editor = app.query("#template-editor")
            assert len(editor) > 0

    async def test_load_request(self) -> None:
        """screen.load_request(req) не крашит."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            req = ParsedRequest(
                method="POST",
                url="http://example.com/login",
                headers={"Host": "example.com"},
                body="user=admin&pass=secret",
            )
            screen = app.query_one(IntruderScreen)
            screen.load_request(req)
            await pilot.pause()
            # Нет исключения — тест пройден

    async def test_small_payload_file_loads_eagerly(self, tmp_path) -> None:
        """A small file (below _EAGER_LOAD_MAX_BYTES) loads as a plain list
        and is fully reflected in the payload list preview."""
        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(IntruderScreen)
            path = tmp_path / "small.txt"
            path.write_text("admin\nroot\nguest\n", encoding="utf-8")

            await screen._load_file_async(str(path), 0)
            await pilot.pause()

            assert screen._payloads[0] == ["admin", "root", "guest"]

    async def test_large_payload_file_installs_file_payload_source(self, tmp_path) -> None:
        """A file above _EAGER_LOAD_MAX_BYTES is installed as a
        FilePayloadSource immediately (usable for Start Attack right away)
        and its line count streams in the background without blocking."""
        from pentool.modules.intruder import FilePayloadSource

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(IntruderScreen)
            # Force the "large file" branch regardless of actual disk size —
            # avoids writing an actual multi-MB fixture file for the test.
            screen._EAGER_LOAD_MAX_BYTES = 0
            path = tmp_path / "big.txt"
            path.write_text("p1\np2\np3\np4\np5\n", encoding="utf-8")

            await screen._load_file_async(str(path), 0)
            await pilot.pause()

            assert isinstance(screen._payloads[0], FilePayloadSource)
            assert screen._payloads[0].cached_count == 5
            assert screen._payload_load_in_progress is False

    async def test_add_payload_blocked_on_file_backed_set(self, tmp_path) -> None:
        """Manually adding a payload to a file-backed set is refused (with
        a warning notification), not silently converted/appended to."""
        from pentool.modules.intruder import FilePayloadSource

        app = PentoolApp()
        app._skip_project_guard = True
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            await pilot.press("I")
            await pilot.pause()
            await pilot.pause()

            screen = app.query_one(IntruderScreen)
            path = tmp_path / "big.txt"
            path.write_text("p1\np2\n", encoding="utf-8")
            screen._payloads[0] = FilePayloadSource(str(path), count=2)

            screen._add_payload_manual()
            await pilot.pause()
            # No exception, and no dialog push crash — the set stays a
            # FilePayloadSource (not silently mutated into a list).
            assert isinstance(screen._payloads[0], FilePayloadSource)

