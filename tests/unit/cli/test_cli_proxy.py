"""Unit tests: cli/proxy.py — `pentool proxy start/status/history/ca-info`."""

from __future__ import annotations

import sys
import types
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from pentool.cli.proxy import proxy


@contextmanager
def _fake_socket(connect_ex_result):
    """Substitute sys.modules['socket'] so the local `import socket` in
    proxy_status uses a deterministic connect_ex result."""
    class FakeSockType:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, t):
            pass

        def connect_ex(self, addr):
            return connect_ex_result

    fake = types.ModuleType("socket")
    fake.socket = FakeSockType
    fake.AF_INET = 2
    fake.SOCK_STREAM = 1
    real = sys.modules.get("socket")
    sys.modules["socket"] = fake
    try:
        yield
    finally:
        if real is not None:
            sys.modules["socket"] = real
        else:
            del sys.modules["socket"]


def _fake_server():
    server = MagicMock()
    server.scope = []
    server.intercept_enabled = False
    server.serve_forever = AsyncMock()
    server.set_scope = MagicMock()
    return server


def test_proxy_start_basic(tmp_path):
    server = _fake_server()
    cfg = MagicMock(cert_dir=str(tmp_path / "certs"), db_path=str(tmp_path / "p.db"),
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI:
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start", "--port", "9090", "--host", "0.0.0.0"],
                               input="")
    assert r.exit_code == 0
    assert "Starting proxy on 0.0.0.0:9090" in r.output
    assert server.serve_forever.called


def test_proxy_start_with_scope(tmp_path):
    server = _fake_server()
    cfg = MagicMock(cert_dir=str(tmp_path / "certs"), db_path=str(tmp_path / "p.db"),
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI:
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start", "--scope", "a.com, b.com"], input="")
    assert server.set_scope.called
    assert r.exit_code == 0


def test_proxy_start_init_db_warns_on_error(tmp_path):
    server = _fake_server()
    cfg = MagicMock(cert_dir=str(tmp_path / "certs"), db_path=str(tmp_path / "p.db"),
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI, \
         patch("pentool.core.db_schema.init_db_sync", side_effect=Exception("no db")):
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start"], input="")
    assert r.exit_code == 0
    assert "could not init database" in r.output


def test_proxy_start_cert_dir_from_cfg(tmp_path):
    server = _fake_server()
    cfg = MagicMock(cert_dir=str(tmp_path / "mycerts"), db_path=None,
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI:
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start"], input="")
    assert r.exit_code == 0


def test_proxy_start_echoes_nonempty_scope(tmp_path):
    server = _fake_server()
    server.scope = ["a.com", "b.com"]
    cfg = MagicMock(cert_dir=str(tmp_path / "certs"), db_path=str(tmp_path / "p.db"),
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI:
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start"], input="")
    assert r.exit_code == 0
    assert "a.com" in r.output


def test_proxy_start_keyboard_interrupt_stops(tmp_path):
    server = _fake_server()
    server.serve_forever = AsyncMock(side_effect=KeyboardInterrupt)
    cfg = MagicMock(cert_dir=str(tmp_path / "certs"), db_path=str(tmp_path / "p.db"),
                    log_level="INFO", log_file=str(tmp_path / "log"))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.cli.proxy.setup_logging"), \
         patch("pentool.api.proxy_api.ProxyAPI") as ProxyAPI:
        ProxyAPI.return_value.create_proxy.return_value = server
        r = CliRunner().invoke(proxy, ["start"], input="")
    assert r.exit_code == 0
    assert "Proxy stopped." in r.output


def test_proxy_status_running():
    with _fake_socket(0):  # connect_ex returns 0 → port open
        r = CliRunner().invoke(proxy, ["status", "--port", "8080"])
    assert r.exit_code == 0
    assert "RUNNING" in r.output


def test_proxy_status_not_running():
    with _fake_socket(111):  # connection refused
        r = CliRunner().invoke(proxy, ["status", "--port", "9999"])
    assert "NOT running" in r.output


def test_proxy_history_missing_db(tmp_path):
    r = CliRunner().invoke(proxy, ["history", "--db", str(tmp_path / "nope.db")])
    assert r.exit_code == 1
    assert "Database not found" in r.output


def test_proxy_history_empty(tmp_path):
    db = tmp_path / "hist.db"
    db.write_bytes(b"sqlite")
    storage = MagicMock()
    storage.init_db = AsyncMock()
    storage.get_metadata_batch = AsyncMock(return_value=[])
    with patch("pentool.storage.http_storage.HttpStorage", return_value=storage):
        r = CliRunner().invoke(proxy, ["history", "--db", str(db)])
    assert r.exit_code == 0
    assert "No requests found." in r.output


def test_proxy_history_renders_rows(tmp_path):
    db = tmp_path / "hist.db"
    db.write_bytes(b"sqlite")
    storage = MagicMock()
    storage.init_db = AsyncMock()
    storage.get_metadata_batch = AsyncMock(return_value=[
        {"id": 1, "method": "GET", "status_code": 200,
         "url": "http://example.com/" + "x" * 100},
    ])
    with patch("pentool.storage.http_storage.HttpStorage", return_value=storage):
        r = CliRunner().invoke(proxy, ["history", "--db", str(db)])
    assert r.exit_code == 0
    assert "GET" in r.output
    assert "200" in r.output


def test_proxy_history_filters_method_host(tmp_path):
    db = tmp_path / "hist.db"
    db.write_bytes(b"sqlite")
    storage = MagicMock()
    storage.init_db = AsyncMock()
    storage.get_metadata_batch = AsyncMock(return_value=[])
    with patch("pentool.storage.http_storage.HttpStorage", return_value=storage) as HS:
        r = CliRunner().invoke(proxy, ["history", "--db", str(db), "--method", "post",
                                       "--host", "example"])
    assert r.exit_code == 0
    kwargs = storage.get_metadata_batch.call_args.kwargs
    assert kwargs["filters"] == {"method": ["POST"], "host": "example"}


def test_proxy_ca_info_existing(tmp_path):
    (tmp_path / "ca.crt").write_text("CERT")
    cfg = MagicMock(cert_dir=str(tmp_path))
    with patch("pentool.cli.proxy.get_config", return_value=cfg):
        r = CliRunner().invoke(proxy, ["ca-info"])
    assert r.exit_code == 0
    assert "CA certificate" in r.output


def test_proxy_ca_info_generates(tmp_path):
    cfg = MagicMock(cert_dir=str(tmp_path))
    with patch("pentool.cli.proxy.get_config", return_value=cfg), \
         patch("pentool.utils.cert.generate_ca_cert",
               return_value=(str(tmp_path / "ca.crt"), "key.pem")) as gen:
        r = CliRunner().invoke(proxy, ["ca-info"])
    assert r.exit_code == 0
    gen.assert_called_once()
    assert "generated" in r.output
