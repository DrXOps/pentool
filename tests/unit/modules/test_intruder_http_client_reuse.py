"""Unit tests: БАГ-D — HTTPClient reuse in IntruderAttack.run().

Verifies that IntruderAttack.run() creates a single HTTPClient shared
across all requests in an attack (instead of opening/closing a new
TCP+TLS connection per request), and that it is closed after the run
completes when the attack owns the client (not injected by the caller).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aioresponses import aioresponses

from pentool.modules.intruder import AttackType, IntruderAttack, IntruderConfig


def _make_config(n_payloads: int = 3) -> IntruderConfig:
    return IntruderConfig(
        template="GET /§FUZZ§ HTTP/1.1\r\nHost: example.com\r\n\r\n",
        attack_type=AttackType.SNIPER,
        payload_sets=[[f"p{i}" for i in range(n_payloads)]],
        threads=5,
        delay_ms=0,
        timeout=5,
    )


@pytest.mark.asyncio
class TestHTTPClientReuse:
    async def test_single_client_created_per_run(self) -> None:
        """run() must instantiate HTTPClient exactly once, not once per request."""
        config = _make_config(n_payloads=5)
        attack = IntruderAttack(config)

        created = []
        from pentool.utils.http_client import HTTPClient as RealHTTPClient

        class TrackingClient(RealHTTPClient):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                created.append(self)

        with patch("pentool.utils.http_client.HTTPClient", TrackingClient):
            with aioresponses() as m:
                for _ in range(5):
                    m.get("http://example.com/p0", status=200, body=b"ok")
                    m.get("http://example.com/p1", status=200, body=b"ok")
                    m.get("http://example.com/p2", status=200, body=b"ok")
                    m.get("http://example.com/p3", status=200, body=b"ok")
                    m.get("http://example.com/p4", status=200, body=b"ok")

                results = []
                await attack.run(
                    on_result=results.append,
                    on_progress=lambda done, total: None,
                )

        assert len(created) == 1, f"Expected exactly 1 HTTPClient, got {len(created)}"
        assert len(results) == 5

    async def test_owned_client_is_closed_after_run(self) -> None:
        """When run() creates its own client, it must be closed when done."""
        config = _make_config(n_payloads=2)
        attack = IntruderAttack(config)

        close_calls = []
        from pentool.utils.http_client import HTTPClient as RealHTTPClient

        class TrackingClient(RealHTTPClient):
            async def close(self):
                close_calls.append(self)
                await super().close()

        with patch("pentool.utils.http_client.HTTPClient", TrackingClient):
            with aioresponses() as m:
                m.get("http://example.com/p0", status=200, body=b"ok")
                m.get("http://example.com/p1", status=200, body=b"ok")

                await attack.run(
                    on_result=lambda r: None,
                    on_progress=lambda done, total: None,
                )

        assert len(close_calls) == 1

    async def test_injected_client_is_not_closed(self) -> None:
        """When an HTTPClient is injected via constructor, run() must not close it —
        the caller owns its lifecycle."""
        from pentool.utils.http_client import HTTPClient

        injected = HTTPClient(timeout=5)
        injected.close = AsyncMock(wraps=injected.close)

        config = _make_config(n_payloads=2)
        attack = IntruderAttack(config, http_client=injected)

        with aioresponses() as m:
            m.get("http://example.com/p0", status=200, body=b"ok")
            m.get("http://example.com/p1", status=200, body=b"ok")

            await attack.run(
                on_result=lambda r: None,
                on_progress=lambda done, total: None,
            )

        injected.close.assert_not_called()
        await injected.close()

    async def test_all_requests_share_client_and_get_responses(self) -> None:
        """Sanity check: every request in the attack still gets a valid result
        when using the shared client."""
        config = _make_config(n_payloads=4)
        attack = IntruderAttack(config)

        with aioresponses() as m:
            for i in range(4):
                m.get(f"http://example.com/p{i}", status=200, body=f"body{i}".encode())

            results = []
            await attack.run(
                on_result=results.append,
                on_progress=lambda done, total: None,
            )

        assert len(results) == 4
        assert all(r.response_status == 200 for r in results)
        assert all(r.error is None for r in results)
