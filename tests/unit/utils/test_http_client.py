"""Unit tests: utils/http_client.py — the aiohttp-based HTTP client."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pentool.utils.http_client import HTTPClient
from pentool.utils.parser import ParsedRequest


def _fake_resp(status=200, body=b"ok", headers=None, reason="OK", charset="utf-8"):
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    resp.charset = charset
    resp.headers = headers or {"content-type": "text/html"}
    resp.read = AsyncMock(return_value=body)
    return resp


def _fake_session(resp):
    """Session whose request() returns an async-CM wrapping `resp`."""
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session.request = MagicMock(return_value=cm)
    session.closed = False
    session.close = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_send_basic_and_response():
    session = _fake_session(_fake_resp(body=b"hello"))
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(method="GET", url="http://example.com/", headers={"Host": "example.com"})
    parsed = await client.send(req)
    assert parsed.status == 200
    assert parsed.body == "hello"
    assert parsed._raw_body == b"hello"


@pytest.mark.asyncio
async def test_send_strips_hop_by_hop_headers():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(
        method="GET", url="http://x/",
        headers={"Host": "x", "Connection": "close",
                 "Transfer-Encoding": "chunked",
                 "Keep-Alive": "timeout=5", "Accept": "text/html"},
    )
    await client.send(req)
    kwargs = session.request.call_args.kwargs
    send_headers = kwargs["headers"]
    assert "Host" not in send_headers
    assert "Connection" not in send_headers
    assert "Transfer-Encoding" not in send_headers
    assert "Keep-Alive" not in send_headers
    assert send_headers.get("Accept") == "text/html"


@pytest.mark.asyncio
async def test_send_strips_brotli_from_accept_encoding():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(
        method="GET", url="http://x/",
        headers={"Accept-Encoding": "gzip, br, zstd, deflate"},
    )
    await client.send(req)
    send_headers = session.request.call_args.kwargs["headers"]
    ae = send_headers["Accept-Encoding"]
    assert "br" not in ae
    assert "zstd" not in ae
    assert "gzip" in ae
    assert "deflate" in ae


@pytest.mark.asyncio
async def test_send_accept_encoding_empty_becomes_default():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(method="GET", url="http://x/", headers={"Accept-Encoding": "br"})
    await client.send(req)
    assert session.request.call_args.kwargs["headers"]["Accept-Encoding"] == "gzip, deflate"


@pytest.mark.asyncio
async def test_send_extra_headers_injected():
    session = _fake_session(_fake_resp())
    client = HTTPClient(extra_headers={"X-Scan": "marker"})
    client._session = session
    req = ParsedRequest(method="GET", url="http://x/", headers={"Accept": "*/*"})
    await client.send(req)
    assert session.request.call_args.kwargs["headers"]["X-Scan"] == "marker"


@pytest.mark.asyncio
async def test_send_proxy_url():
    session = _fake_session(_fake_resp())
    client = HTTPClient(proxy_url="http://proxy:8080")
    client._session = session
    req = ParsedRequest(method="GET", url="http://x/", headers={})
    await client.send(req)
    assert session.request.call_args.kwargs["proxy"] == "http://proxy:8080"


@pytest.mark.asyncio
async def test_send_calls_on_request_sent_callback():
    session = _fake_session(_fake_resp(body=b"cb"))
    seen = []
    client = HTTPClient(on_request_sent=lambda req, resp: seen.append((req.method, resp.body)))
    client._session = session
    req = ParsedRequest(method="POST", url="http://x/", headers={"Content-Type": "text/plain"}, body="data")
    await client.send(req)
    assert seen == [("POST", "cb")]


@pytest.mark.asyncio
async def test_send_body_data():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(method="POST", url="http://x/", headers={}, body="abc")
    await client.send(req)
    assert session.request.call_args.kwargs["data"] == b"abc"


@pytest.mark.asyncio
async def test_send_no_body():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    req = ParsedRequest(method="GET", url="http://x/", headers={}, body=None)
    await client.send(req)
    assert session.request.call_args.kwargs["data"] is None


@pytest.mark.asyncio
async def test_get_convenience():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    parsed = await client.get("http://x/", headers={"Accept": "text/html"})
    assert session.request.call_args.args[0] == "GET"
    assert parsed.status == 200


@pytest.mark.asyncio
async def test_post_convenience():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    parsed = await client.post("http://x/", body="a=b", headers={"X": "1"})
    assert session.request.call_args.args[0] == "POST"
    assert parsed.status == 200


@pytest.mark.asyncio
async def test_send_raw_parses():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    # Real parse then send — no mock needed, uses the real parser.
    parsed = await client.send_raw("GET http://x/ HTTP/1.1\r\nHost: x\r\n\r\n")
    assert parsed.status == 200


@pytest.mark.asyncio
async def test_close_session():
    session = _fake_session(_fake_resp())
    client = HTTPClient()
    client._session = session
    await client.close()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_session_lazily():
    client = HTTPClient()
    assert client._session is None
    session = await client._get_session()
    assert session is not None
    # second call returns same
    assert await client._get_session() is session


@pytest.mark.asyncio
async def test_async_context_manager():
    client = HTTPClient()
    async with client as c:
        assert c is client
