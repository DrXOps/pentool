"""Unit tests: storage/large_body_handler.py — bodies > 1 MB stored on disk."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pentool.storage.large_body_handler import LargeBodyHandler, THRESHOLD


def test_is_large_none_false():
    assert LargeBodyHandler.is_large(None) is False


def test_is_large_bytes():
    assert LargeBodyHandler.is_large(bytes(THRESHOLD + 1)) is True
    assert LargeBodyHandler.is_large(bytes(THRESHOLD)) is False


def test_is_large_str():
    assert LargeBodyHandler.is_large("x" * (THRESHOLD + 1)) is True
    assert LargeBodyHandler.is_large("x" * 10) is False


def test_store_then_load_roundtrip(tmp_path):
    cls = LargeBodyHandler
    with patch.object(cls, "BASE_DIR", tmp_path):
        path = cls.store(42, "req", b"\x00\x01payload")
        assert Path(path).exists()
        assert cls.load(path) == b"\x00\x01payload"
        assert path.endswith("42_req.bin")


def test_store_creates_dir(tmp_path):
    target = tmp_path / "nested" / "bodies"
    with patch.object(LargeBodyHandler, "BASE_DIR", target):
        path = LargeBodyHandler.store(1, "resp", b"x")
    assert target.is_dir()
    assert Path(path).exists()


def test_delete_removes_file(tmp_path):
    cls = LargeBodyHandler
    with patch.object(cls, "BASE_DIR", tmp_path):
        path = cls.store(7, "resp", b"data")
        cls.delete(path)
        assert not Path(path).exists()


def test_delete_missing_no_error(tmp_path):
    LargeBodyHandler.delete(str(tmp_path / "does_not_exist.bin"))  # no raise


def test_delete_logs_on_error(tmp_path):
    with patch("pentool.storage.large_body_handler.logger.warning") as warn, \
         patch("pathlib.Path.unlink", side_effect=OSError("locked")):
        LargeBodyHandler.delete(str(tmp_path / "x.bin"))
    # unlink raises → warning logged, no re-raise
    warn.assert_called()
