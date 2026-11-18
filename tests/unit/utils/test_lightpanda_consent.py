"""Загрузка JS-браузера Lightpanda — только с согласия пользователя.

Одноразовая загрузка весит ~150 МиБ (v0.3.7 — 157 502 440 байт). Молча качать
такой объём нельзя, поэтому `ensure_lightpanda_with_consent` спрашивает, помнит
отказ и не трогает CI (там нет TTY).
"""

from __future__ import annotations

import pytest

from pentool.utils import lightpanda


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Изолирует маркер отказа и подменяет установку/поиск бинарника."""
    marker = tmp_path / "lightpanda-declined"
    monkeypatch.setattr(lightpanda, "_decline_marker", lambda: marker)
    monkeypatch.setattr(lightpanda, "find_lightpanda_binary", lambda: None)

    calls: list[bool] = []

    def fake_install() -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(lightpanda, "ensure_lightpanda_installed_sync", fake_install)
    return marker, calls


def test_binary_present_returns_true_without_prompt(monkeypatch, isolated):
    _, calls = isolated
    monkeypatch.setattr(lightpanda, "find_lightpanda_binary", lambda: "/usr/bin/lightpanda")
    assert lightpanda.ensure_lightpanda_with_consent() is True
    assert calls == [], "установка не должна запускаться, если браузер уже есть"


def test_recorded_decline_is_respected(monkeypatch, isolated):
    marker, calls = isolated
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("declined\n", encoding="utf-8")

    assert lightpanda.ensure_lightpanda_with_consent() is False
    assert calls == [], "после отказа не спрашиваем и не качаем повторно"


def test_no_tty_never_downloads(monkeypatch, isolated):
    _, calls = isolated
    monkeypatch.setattr(lightpanda.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert lightpanda.ensure_lightpanda_with_consent() is False
    assert calls == [], "в CI/пайпе загрузка не запускается без --install-browser"


def test_answer_no_remembers_decline(monkeypatch, isolated):
    marker, calls = isolated
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    assert lightpanda.ensure_lightpanda_with_consent() is False
    assert calls == []
    assert marker.is_file(), "отказ должен запоминаться, чтобы не спрашивать снова"


def test_answer_yes_downloads(monkeypatch, isolated):
    _, calls = isolated
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda *_: "y")

    assert lightpanda.ensure_lightpanda_with_consent() is True
    assert calls == [True]


def test_auto_yes_skips_the_question(monkeypatch, isolated):
    _, calls = isolated

    def boom(*_a, **_kw):
        raise AssertionError("в режиме --install-browser вопрос задавать нельзя")

    monkeypatch.setattr("builtins.input", boom)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert lightpanda.ensure_lightpanda_with_consent(auto_yes=True) is True
    assert calls == [True]
