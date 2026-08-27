"""Unit tests for pentool/utils/auth_login.py.

Covers the pure HTML/Set-Cookie parsers (no network) plus the login flow
orchestrated over a fake http_client (no real HTTP).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pentool.utils.auth_login import (
    build_session_headers,
    extract_phpsessid,
    extract_user_token,
)

# ── pure parsers ─────────────────────────────────────────────────────────────

class TestExtractUserToken:
    def test_normal_attribute_order(self) -> None:
        html = "<input type='hidden' name='user_token' value='0123456789abcdef0123456789abcdef'>"
        assert extract_user_token(html) == "0123456789abcdef0123456789abcdef"

    def test_reversed_attribute_order(self) -> None:
        html = '<input value="00112233445566778899aabbccddeeff" name="user_token">'
        assert extract_user_token(html) == "00112233445566778899aabbccddeeff"

    def test_missing_returns_none(self) -> None:
        assert extract_user_token("<html><body>no form</body></html>") is None

    def test_non_hex_token_ignored(self) -> None:
        html = "<input name='user_token' value='NOTAHEXVALUE123456789'>"
        assert extract_user_token(html) is None


class TestExtractPhpsessid:
    def test_from_string(self) -> None:
        assert extract_phpsessid("PHPSESSID=abc123; path=/; httponly") == "abc123"

    def test_from_list(self) -> None:
        assert extract_phpsessid([
            "lang=en; path=/", "PHPSESSID=xyz789; path=/",
        ]) == "xyz789"

    def test_missing_returns_none(self) -> None:
        assert extract_phpsessid("lang=en; path=/") is None


# ── login flow over a fake http_client ───────────────────────────────────────

_LICENSE_BODY = "<html><body>Login</body></html>"


def _ok_response(status: int, body: str = "", headers=None):
    from pentool.utils.parser import ParsedResponse

    return ParsedResponse(status=status, headers=headers or {}, body=body)


class _FakeClient:
    """Scripted http_client.send returning staged responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent: list = []
        self.send = AsyncMock(side_effect=self._handle)
        self.closed = False

    async def _handle(self, request):
        self.sent.append(request)
        if not self._responses:
            return _ok_response(500)
        return self._responses.pop(0)

    async def close(self):
        self.closed = True


class TestBuildSessionHeaders:
    @pytest.mark.asyncio
    async def test_successful_login_returns_cookie(self) -> None:
        client = _FakeClient([
            # GET /login.php -> 200 + Set-Cookie + CSRF token in body
            _ok_response(200, _LICENSE_BODY, {"Set-Cookie": "PHPSESSID=sess1; path=/"}),
            # POST /login.php -> 200 (accepted)
            _ok_response(200, "", {"Set-Cookie": "PHPSESSID=sess2; path=/"}),
            # GET /index.php -> 200 (logged in)
            _ok_response(200, "<html>index</html>"),
        ])
        import pentool.utils.auth_login as al

        # Patch the CSRF parser so we don't depend on DVWA HTML shape; the real
        # extract_phpsessid reads Set-Cookie as the production flow does.
        orig_token = al.extract_user_token
        al.extract_user_token = lambda html: "0123456789abcdef0123456789abcdef"
        try:
            headers = await build_session_headers(
                url="http://dvwa.local:7474", username="admin", password="password",
                use_cache=False, http_client=client,
            )
        finally:
            al.extract_user_token = orig_token

        assert "Cookie" in headers
        # After the POST the session id may rotate; the final cookie reflects
        # the re-read Set-Cookie (sess2).
        assert "PHPSESSID=sess2" in headers["Cookie"], headers

    @pytest.mark.asyncio
    async def test_redirect_to_login_raises(self) -> None:
        import pentool.utils.auth_login as al

        client = _FakeClient([
            _ok_response(200, _LICENSE_BODY, {"Set-Cookie": "PHPSESSID=badsess; path=/"}),
            _ok_response(302, "", {"Location": "/login.php"}),
            _ok_response(302, "", {"Location": "/login.php"}),
        ])
        orig = al.extract_user_token
        al.extract_user_token = lambda html: "0123456789abcdef0123456789abcdef"
        try:
            with pytest.raises(RuntimeError, match="login.php"):
                await build_session_headers(
                    url="http://x.local", username="u", password="p",
                    use_cache=False, http_client=client,
                )
        finally:
            al.extract_user_token = orig

    @pytest.mark.asyncio
    async def test_owned_client_is_closed(self) -> None:
        """When no http_client is supplied, build_session_headers creates its
        own and closes it (no leaked connection)."""
        from unittest.mock import patch

        import pentool.utils.auth_login as al

        closed_by_app = []

        class _OwnedClient:
            def __init__(self, *a, **k):
                self.closed = False

            async def send(self, request):
                return _ok_response(200, "", {"Set-Cookie": "PHPSESSID=own; path=/"})

            async def close(self):
                self.closed = True
                closed_by_app.append(True)

        orig_token = al.extract_user_token
        al.extract_user_token = lambda html: "0123456789abcdef0123456789abcdef"
        try:
            al._SESSION_CACHE.clear()
            with patch("pentool.utils.http_client.HTTPClient", _OwnedClient):
                await build_session_headers(
                    url="http://own.local", username="u", password="p", use_cache=False,
                )
        finally:
            al.extract_user_token = orig_token

        assert closed_by_app, "owned HTTPClient was not closed (connection leak)"
