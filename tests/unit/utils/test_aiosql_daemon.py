"""Unit tests: utils/aiosql_daemon.py — aiosqlite worker thread as daemon."""

from __future__ import annotations

from unittest.mock import MagicMock

from pentool.utils.aiosql_daemon import make_aiosqlite_daemon


def test_marks_thread_daemon():
    db = MagicMock()
    db._thread = MagicMock()
    db._thread.daemon = True
    out = make_aiosqlite_daemon(db)
    assert out is db
    assert db._thread.daemon is True


def test_no_thread_attribute_is_safe():
    db = MagicMock()
    del db._thread  # connection without a worker thread attribute
    # must not raise
    assert make_aiosqlite_daemon(db) is db


def test_exception_is_swallowed():
    db = MagicMock()
    db._thread.daemon = "nope"  # pathological — setting raised
    # must not raise
    assert make_aiosqlite_daemon(db) is db
