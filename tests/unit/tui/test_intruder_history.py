"""`screen.app` is a read-only property: patch the module-level lookup instead.

The method reads `self.app`, so the test injects a fake via `__getattribute__` on a bare
object built from the class (no DOM, no Textual app needed).
"""

from __future__ import annotations

from types import SimpleNamespace

from pentool.tui.screens.intruder.screen import IntruderScreen


class _Service:
    def __init__(self) -> None:
        self.stored: list = []

    async def store_request(self, entry):
        self.stored.append(entry)
        return 1


class _Host(IntruderScreen):
    """Bare instance: the recorder only needs `app`, `run_worker` and the logger."""

    def __init__(self, service, workers):  # noqa: D401 - test double
        object.__setattr__(self, "_fake_app", SimpleNamespace(_proxy_service=service))
        object.__setattr__(self, "_workers", workers)

    @property
    def app(self):  # type: ignore[override]
        return self._fake_app

    def run_worker(self, coro, **kwargs):
        self._workers.append(coro)


def test_exchange_is_stored_with_request_and_response() -> None:
    service = _Service()
    workers: list = []
    host = _Host(service, workers)

    result = SimpleNamespace(
        request_raw="GET /x HTTP/1.1\r\nHost: a.test\r\n\r\n",
        response_status=200,
        response_body="ok",
    )
    host._record_to_proxy_history(result)

    assert len(workers) == 1, "запись уходит в прокси-сервис отдельной задачей"


def test_missing_proxy_service_is_not_an_error() -> None:
    host = _Host(None, [])
    host._record_to_proxy_history(SimpleNamespace(request_raw="GET / HTTP/1.1\r\n\r\n"))


def test_empty_request_raw_is_skipped() -> None:
    workers: list = []
    host = _Host(_Service(), workers)
    host._record_to_proxy_history(SimpleNamespace(request_raw="   "))
    assert workers == [], "пустой запрос не должен попадать в историю"
