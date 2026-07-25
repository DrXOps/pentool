"""Unit-тесты для pentool/core/utils.py."""

import asyncio
import pytest
from pentool.core.utils import run_async_sync


class TestRunAsyncSync:
    def test_simple_return_value(self):
        """run_async_sync возвращает результат корутины."""
        async def _coro():
            return 42
        assert run_async_sync(_coro()) == 42

    def test_async_sleep_and_return(self):
        """run_async_sync дожидается async операций."""
        async def _coro():
            await asyncio.sleep(0.01)
            return "done"
        assert run_async_sync(_coro()) == "done"

    def test_exception_propagated(self):
        """Исключение из корутины пробрасывается наружу."""
        async def _coro():
            raise ValueError("test error")
        with pytest.raises(ValueError, match="test error"):
            run_async_sync(_coro())

    def test_timeout_raises_timeout_error(self):
        """Если корутина не завершается за timeout → TimeoutError."""
        async def _coro():
            await asyncio.sleep(10)
            return "never"
        with pytest.raises(TimeoutError, match="timed out after 0.1s"):
            run_async_sync(_coro(), timeout=0.1)

    def test_none_return(self):
        """Корутина без return → None."""
        async def _coro():
            await asyncio.sleep(0.001)
        assert run_async_sync(_coro()) is None

    def test_list_return(self):
        """run_async_sync корректно возвращает сложные типы."""
        async def _coro():
            return [1, 2, {"key": "value"}]
        result = run_async_sync(_coro())
        assert result == [1, 2, {"key": "value"}]

    def test_custom_timeout(self):
        """Параметр timeout работает."""
        async def _coro():
            await asyncio.sleep(0.05)
            return "ok"
        # Должен успеть за 1s
        assert run_async_sync(_coro(), timeout=1.0) == "ok"
