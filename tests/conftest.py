"""Common pytest fixtures for PenTool tests.

All fixtures use pytest_asyncio in STRICT mode.
Async fixtures are declared with @pytest_asyncio.fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

# PRO submodule: extend pentool package paths so imports like
# `from pentool.plugins.builtin.payloads_pro import ...` resolve
# from pro/pentool/... when the submodule is checked out.
_pro_root = Path(__file__).parent.parent / "pro"
if _pro_root.exists():
    import importlib
    import pentool
    import pentool.modules
    import pentool.plugins
    import pentool.plugins.builtin

    for _pkg, _rel in [
        (pentool,               "pentool"),
        (pentool.modules,       "pentool/modules"),
        (pentool.plugins,       "pentool/plugins"),
        (pentool.plugins.builtin, "pentool/plugins/builtin"),
    ]:
        _extra = str(_pro_root / _rel)
        if _extra not in _pkg.__path__:
            _pkg.__path__.append(_extra)

import pytest
import pytest_asyncio

from pentool.core.config import Config, set_config
from pentool.core.database import init_db
from pentool.utils.parser import ParsedRequest, ParsedResponse


def has_scanner_module():
    """Check if scanner module (PRO) is available."""
    try:
        import pentool.modules.scanner  # noqa: F401
        return True
    except ImportError:
        return False


pytest_skip_if_no_scanner = pytest.mark.skipif(
    not has_scanner_module(),
    reason="Scanner module (PRO) not available"
)


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: integration tests (TUI, network)")
    config.addinivalue_line("markers", "snapshot: visual regression tests")
    config.addinivalue_line("markers", "slow: slow tests")


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Test configuration with isolated temporary paths."""
    cfg = Config(
        proxy_host="127.0.0.1",
        proxy_port=19081,
        db_path=str(tmp_path / "test.db"),
        log_file=str(tmp_path / "test.log"),
        cert_dir=str(tmp_path / "certs"),
        plugins_dir=str(tmp_path / "plugins"),
        scope=[],
        intercept_enabled=False,
    )
    set_config(cfg)
    return cfg


@pytest_asyncio.fixture
async def test_db(test_config: Config) -> str:
    """Initialized test database (tables created)."""
    await init_db(test_config.db_path)
    return test_config.db_path


@pytest_asyncio.fixture
async def http_storage(tmp_path: Path):
    """Ready HttpStorage with a temporary database."""
    from pentool.storage.http_storage import HttpStorage
    storage = HttpStorage()
    db_path = str(tmp_path / "history.db")
    await storage.init_db(db_path)
    yield storage
    await storage.close()


@pytest.fixture
def sample_request() -> ParsedRequest:
    """Typical GET request for tests."""
    return ParsedRequest(
        method="GET",
        url="http://example.com/api/users?page=1",
        headers={
            "Host": "example.com",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
        body="",
    )


@pytest.fixture
def sample_post_request() -> ParsedRequest:
    """POST request with a body."""
    return ParsedRequest(
        method="POST",
        url="https://example.com/login",
        headers={
            "Host": "example.com",
            "Content-Type": "application/json",
            "Content-Length": "35",
        },
        body='{"username": "admin", "password": "secret"}',
    )


@pytest.fixture
def sample_response() -> ParsedResponse:
    """Typical 200 response."""
    return ParsedResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/json",
            "Content-Length": "42",
        },
        body='{"users": [{"id": 1, "name": "Alice"}]}',
    )


@pytest.fixture
def sample_404_response() -> ParsedResponse:
    """404 response."""
    return ParsedResponse(
        status=404,
        reason="Not Found",
        headers={"Content-Type": "text/html"},
        body="<h1>Not Found</h1>",
    )


@pytest.fixture
def mock_proxy_server():
    """Mock ProxyServer with standard behavior."""
    mock = MagicMock()
    mock.is_running = True  # @property on ProxyServer, not callable
    mock.port = 8080
    mock.host = "127.0.0.1"
    mock.intercept_enabled = False
    mock.scope = []
    mock.match_replace_rules = []
    mock.requests = []
    mock.get_status.return_value = {
        "running": True,
        "host": "127.0.0.1",
        "port": 8080,
        "intercept_enabled": False,
        "scope": [],
        "rules_count": 0,
        "requests_count": 0,
        "waiting_count": 0,
    }
    mock.get_requests.return_value = []
    mock.get_scope.return_value = []  # Remove if not needed
    mock._find_request.return_value = None
    return mock
