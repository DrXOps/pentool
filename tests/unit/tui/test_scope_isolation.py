"""Regression tests: per-project Scope isolation on project switch.

User-selectable behavior ("новый проект = пустой скоуп, старый = свой"):
- A brand-NEW project (is_new=True) must NOT inherit the global Config.scope
  (which mirrors whatever the previously-open project last saved) — it starts
  empty.
- An existing/opened project (is_new=False) keeps the current fallback to
  Config.scope when its own DB has no saved scope (so old setups don't regress).

Guards:
  pentool.tui.screens.proxy.screen.ProxyScreen._load_scope_setting
"""

from __future__ import annotations

import pytest

from pentool.core.config import get_config, set_config, Config
from pentool.tui.screens.proxy.screen import ProxyScreen


class _FakeProxy:
    def __init__(self):
        self.scope = []

    def set_scope(self, hosts):
        self.scope = list(hosts)


def _make_screen(db_path: str) -> ProxyScreen:
    """Minimal ProxyScreen instance without starting Textual (pattern from
    test_proxy_pending_cleanup)."""
    screen = object.__new__(ProxyScreen)
    screen._proxy = _FakeProxy()
    screen._get_proxy = lambda: screen._proxy
    screen._get_db_path = lambda: db_path
    q_exc = Exception("no filter bar mounted")
    screen.query_one = lambda *a, **k: (_ for _ in ()).throw(q_exc)
    return screen


def _pin_global_scope(scope: list[str]) -> None:
    cfg = get_config()
    cfg.scope = list(scope)
    set_config(cfg)


async def _no_db_row(path, key, default=None):
    return default


@pytest.mark.asyncio
async def test_new_project_does_not_inherit_global_scope(tmp_path, monkeypatch):
    """is_new=True → empty scope even though global Config.scope is non-empty."""
    _pin_global_scope(["legacy.example", "old.example"])
    # No per-project row exists in the fresh DB.
    monkeypatch.setattr(
        "pentool.core.db_schema.get_project_setting", _no_db_row
    )
    screen = _make_screen(str(tmp_path / "new.db"))
    await screen._load_scope_setting(is_new=True)
    assert screen._proxy.scope == [], (
        "brand-new project inherited global scope; expected empty"
    )


@pytest.mark.asyncio
async def test_existing_project_falls_back_to_global(tmp_path, monkeypatch):
    """is_new=False with no per-project row → falls back to global Config.scope."""
    _pin_global_scope(["old.example"])
    monkeypatch.setattr(
        "pentool.core.db_schema.get_project_setting", _no_db_row
    )
    screen = _make_screen(str(tmp_path / "existing.db"))
    await screen._load_scope_setting(is_new=False)
    assert screen._proxy.scope == ["old.example"], "existing project lost global scope fallback"


@pytest.mark.asyncio
async def test_is_new_with_saved_project_scope_keeps_own(tmp_path, monkeypatch):
    """is_new=True still honors an actual per-project row if one exists."""
    import json

    async def _own_row(path, key, default=None):
        return json.dumps(["own.example"])

    monkeypatch.setattr(
        "pentool.core.db_schema.get_project_setting", _own_row
    )
    screen = _make_screen(str(tmp_path / "new.db"))
    await screen._load_scope_setting(is_new=True)
    # A real row in the DB wins regardless of is_new.
    assert screen._proxy.scope == ["own.example"]
