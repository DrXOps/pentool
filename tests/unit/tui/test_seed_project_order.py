"""`--url ... --smart` has to switch to the new project BEFORE it captures.

The bug (2026-11-20, user report): ``pentool --url X --smart`` showed an empty
Proxy history although the browser fetch had clearly run. The seed called
``switch_project_db()`` — which fires a worker and returns immediately — and
went on to start the proxy and fetch. The switch worker finished *after* the
fetch, so every captured request was written into the previously open DB (the
default ``pentool.db`` or the last project) and then the freshly created
project was reloaded with zero rows.

The guard is about ordering, not about the DB itself: the seed must wait for
``switch_project_db_awaited()`` to return before the proxy exists and before
the fetch runs. If it ever goes back to the fire-and-forget call, this fails.
"""

from __future__ import annotations

import pytest

from pentool.tui.app import PentoolApp


class _RecordingProjectManager:
    """Stands in for ProjectManager and records which switch call was used."""

    def __init__(self, order: list[tuple[str, object]], *, fail: bool = False) -> None:
        self._order = order
        self._fail = fail

    async def switch_project_db_awaited(self, path: str, is_new: bool = False) -> None:
        self._order.append(("switch-done", path))
        if self._fail:
            raise OSError("cannot create the project database")

    def switch_project_db(self, path: str, is_new: bool = False) -> None:
        # The racing call: returns before the storage is switched.
        self._order.append(("switch-fired-and-forgotten", path))


def _seeded_app(monkeypatch: pytest.MonkeyPatch, order: list[tuple[str, object]], *, fail: bool = False) -> PentoolApp:
    app = PentoolApp()
    app._pm = _RecordingProjectManager(order, fail=fail)  # type: ignore[assignment]
    monkeypatch.setattr(app, "_project_path_for_target", lambda url: "/tmp/new-project.db")
    monkeypatch.setattr(app, "post_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_start_proxy", lambda: order.append(("proxy-start", None)))
    monkeypatch.setattr(app, "_do_real_fetch_sync", lambda urls: order.append(("fetch", tuple(urls))) or True)
    monkeypatch.setattr(
        "pentool.tui.mixins.auto_scope._force_scope_host",
        lambda host, _app: order.append(("scope", host)),
    )
    app._pending_start_smart = True
    app._pending_start_ai = False
    return app


@pytest.mark.asyncio
async def test_seed_waits_for_the_project_switch_before_capturing(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[tuple[str, object]] = []
    app = _seeded_app(monkeypatch, order)

    await app._seed_pending_urls(["https://example.com/"])

    kinds = [kind for kind, _value in order]
    assert ("switch-done", "/tmp/new-project.db") in order
    assert "switch-fired-and-forgotten" not in kinds, "the seed went back to the racing switch call"
    assert kinds.index("switch-done") < kinds.index("proxy-start"), "the proxy was started before the DB was switched"
    assert kinds.index("switch-done") < kinds.index("fetch"), "the fetch ran before the DB was switched"


@pytest.mark.asyncio
async def test_seed_stops_when_the_project_cannot_be_created(monkeypatch: pytest.MonkeyPatch) -> None:
    """No project → no capture: writing the target's traffic into the previous
    project's DB is worse than an aborted seed with a logged reason."""
    order: list[tuple[str, object]] = []
    app = _seeded_app(monkeypatch, order, fail=True)

    await app._seed_pending_urls(["https://example.com/"])

    kinds = [kind for kind, _value in order]
    assert "proxy-start" not in kinds
    assert "fetch" not in kinds
