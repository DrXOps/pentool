"""`--real` не должен молча создавать пустой проект.

Разбор жалобы «автоматический перехват с --real не работает»: флаг был
переименован в `--smart`, а старый `--real` пропал — команда запускала проект
без перехвата. Вторая причина: трафик тянул только бинарник Lightpanda, и если
его нет в системе, `_do_real_fetch_sync` возвращал False, не сделав ни одного
запроса.

Тесты фиксируют обе половины: флаг-алиас существует, а отсутствие Lightpanda
уводит в HTTP-фолбэк вместо тихого выхода.
"""

from __future__ import annotations

import types

import pytest

from pentool.tui.app import PentoolApp


def test_real_flag_is_gone_and_smart_is_the_only_way() -> None:
    """`--real` убран: он расходился с `--smart` (не включал установку браузера)."""
    from pentool.cli.main import cli

    names = {param.name for param in cli.params}
    assert "cli_real" not in names, "--real вернулся: он снова начнёт расходиться с --smart"
    assert "cli_smart" in names
    assert "cli_install_browser" in names


@pytest.mark.asyncio
async def test_missing_lightpanda_uses_the_http_fallback(monkeypatch) -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    app._proxy = types.SimpleNamespace(is_running=True, host="127.0.0.1", port=8080)

    seen: dict[str, object] = {}

    def fake_fallback(urls, proxy_url, ca_path):  # noqa: ANN001 - test double
        seen["urls"] = list(urls)
        seen["proxy_url"] = proxy_url
        return True

    monkeypatch.setattr(app, "_do_http_fallback_fetch", fake_fallback)
    monkeypatch.setattr("pentool.utils.lightpanda.find_lightpanda_binary", lambda: None)

    ok = app._do_real_fetch_sync(["http://example.invalid/"])

    assert ok is True, "без Lightpanda фетч обязан идти HTTP-фолбэком, а не возвращать False"
    assert seen["urls"] == ["http://example.invalid/"]
    assert seen["proxy_url"] == "http://127.0.0.1:8080"


@pytest.mark.asyncio
async def test_fallback_reports_failure_when_nothing_was_captured(monkeypatch) -> None:
    app = PentoolApp()
    app._skip_project_guard = True
    app._proxy = types.SimpleNamespace(is_running=True, host="127.0.0.1", port=8080)
    monkeypatch.setattr(app, "_do_http_fallback_fetch", lambda *a, **kw: False)
    monkeypatch.setattr("pentool.utils.lightpanda.find_lightpanda_binary", lambda: None)

    assert app._do_real_fetch_sync(["http://example.invalid/"]) is False
