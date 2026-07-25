"""Общие фикстуры pytest для тестов PenTool.

Все фикстуры используют pytest_asyncio в STRICT режиме.
Async-фикстуры объявляются через @pytest_asyncio.fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from pentool.core.config import Config, set_config
from pentool.core.database import init_db
from pentool.utils.parser import ParsedRequest, ParsedResponse


def pytest_configure(config):
    """Регистрация кастомных маркеров."""
    config.addinivalue_line("markers", "integration: integration tests (TUI, network)")
    config.addinivalue_line("markers", "snapshot: visual regression tests")
    config.addinivalue_line("markers", "slow: slow tests")


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Тестовая конфигурация с изолированными временными путями."""
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
    """Инициализированная тестовая БД (таблицы созданы)."""
    await init_db(test_config.db_path)
    return test_config.db_path


@pytest_asyncio.fixture
async def http_storage(tmp_path: Path):
    """Готовый HttpStorage с временной БД."""
    from pentool.storage.http_storage import HttpStorage
    storage = HttpStorage()
    db_path = str(tmp_path / "history.db")
    await storage.init_db(db_path)
    yield storage
    await storage.close()


@pytest.fixture
def sample_request() -> ParsedRequest:
    """Типичный GET-запрос для тестов."""
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
    """POST-запрос с телом."""
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
    """Типичный 200 ответ."""
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
    """404 ответ."""
    return ParsedResponse(
        status=404,
        reason="Not Found",
        headers={"Content-Type": "text/html"},
        body="<h1>Not Found</h1>",
    )


@pytest.fixture
def mock_proxy_server():
    """Мок ProxyServer со стандартным поведением."""
    mock = MagicMock()
    mock.is_running = True  # @property на ProxyServer, не callable
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
    mock.get_scope.return_value = []  # Убираем если не нужен
    mock._find_request.return_value = None
    return mock
