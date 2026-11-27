"""`--smart` writes an intent row into history immediately (release queue item 6).

Starting with a target launches the browser for about a second; during that window the history is
empty and reads as "nothing works". The test pins the contract: one row per URL, marked
`fetch started`, and its comment replaced with the outcome when the fetch finishes.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


class _Service:
    def __init__(self) -> None:
        self.stored: list = []
        self.comments: dict[int, str] = {}
        self._next = 1

    async def store_request(self, entry):
        self.stored.append(entry)
        row_id = self._next
        self._next += 1
        return row_id

    async def update_comment(self, row_id: int, comment: str) -> None:
        self.comments[row_id] = comment


def _app(service) -> PentoolApp:
    app = PentoolApp()
    app._skip_project_guard = True
    app._proxy_service = service
    return app


@pytest.mark.asyncio
async def test_pending_rows_are_stored_and_marked() -> None:
    service = _Service()
    app = _app(service)

    rows = await app._store_pending_history_rows(["example.com", "https://other.test/x"])

    assert len(rows) == 2, "one intent row per URL"
    assert [entry.url for entry in service.stored] == ["https://example.com", "https://other.test/x"]
    assert set(service.comments.values()) == {"fetch started"}


@pytest.mark.asyncio
async def test_pending_rows_get_the_result_in_their_comment() -> None:
    service = _Service()
    app = _app(service)
    rows = await app._store_pending_history_rows(["example.com"])

    await app._finalize_pending_history_rows(rows, captured=True)
    assert service.comments[rows[0]] == "captured"

    await app._finalize_pending_history_rows(rows, captured=False)
    assert service.comments[rows[0]] == "no response captured"


@pytest.mark.asyncio
async def test_without_a_service_nothing_raises() -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    app._proxy_service = None

    assert await app._store_pending_history_rows(["example.com"]) == []
    await app._finalize_pending_history_rows([], captured=False)
