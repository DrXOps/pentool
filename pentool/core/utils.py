"""core/utils.py — general-purpose utilities."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_async_sync(coro: Coroutine[Any, Any, T], timeout: float = 15.0) -> T:
    result: list[Any] = []
    exc_box: list[BaseException] = []
    done_event = threading.Event()

    def _run() -> None:
        loop = asyncio.new_event_loop()
        try:
            result.append(loop.run_until_complete(coro))
        except Exception as e:
            exc_box.append(e)
        finally:
            loop.close()
            done_event.set()

    threading.Thread(target=_run, daemon=True).start()
    finished = done_event.wait(timeout=timeout)
    if not finished:
        raise TimeoutError(f"run_async_sync: timed out after {timeout}s")
    if exc_box:
        raise exc_box[0]
    return result[0] if result else None  # type: ignore[return-value]


__all__ = ["run_async_sync"]
