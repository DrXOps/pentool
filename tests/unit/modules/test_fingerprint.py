"""Unit tests for pentool/modules/scanner/fingerprint.py.

Regression coverage for a bug found while auditing checks alongside the
BaseActiveCheck migration (see
MYPLANS/ARCHITECTURE_REFACTOR_PLAN_2026-08-09.md addendum):
TechFingerprinter.fingerprint() read `resp.status_code`/`resp.text`, but
ParsedResponse only has `status`/`body` (aiohttp/requests-style attribute
names that never existed on this dataclass). Every call raised
AttributeError, silently swallowed by the `try/except: logger.debug(...)`
wrapper in ScanEngine.run_active_on_requests — so Tech Fingerprinting
(Phase A.3 of the Scanner modernization plan) was a no-op since its
introduction: tech_profile was always None, so no check was ever skipped
based on stack relevance.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pentool.modules.scanner")

from pentool.modules.scanner.fingerprint import TechFingerprinter, TechProfile
from pentool.utils.parser import ParsedResponse


class _FakeClient:
    def __init__(self, resp: ParsedResponse) -> None:
        self._resp = resp

    async def get(self, url, headers=None):
        return self._resp


class TestFingerprint:
    @pytest.mark.asyncio
    async def test_does_not_raise_attributeerror(self):
        """The core regression: this used to blow up on every call."""
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="hello")
        profile = await TechFingerprinter().fingerprint("http://test/", _FakeClient(resp))
        assert isinstance(profile, TechProfile)

    @pytest.mark.asyncio
    async def test_status_code_populated(self):
        resp = ParsedResponse(status=200, reason="OK", headers={}, body="")
        profile = await TechFingerprinter().fingerprint("http://test/", _FakeClient(resp))
        assert profile.status_code == 200

    @pytest.mark.asyncio
    async def test_server_header_and_php_detection(self):
        resp = ParsedResponse(
            status=200, reason="OK",
            headers={"Server": "Apache", "X-Powered-By": "PHP/8.1"},
            body="",
        )
        profile = await TechFingerprinter().fingerprint("http://test/", _FakeClient(resp))
        assert profile.server_header == "apache"
        assert profile.powered_by == "php/8.1"
        assert profile.is_php is True

    @pytest.mark.asyncio
    async def test_nodejs_detection_from_powered_by(self):
        resp = ParsedResponse(
            status=200, reason="OK", headers={"X-Powered-By": "Express"}, body="",
        )
        profile = await TechFingerprinter().fingerprint("http://test/", _FakeClient(resp))
        assert profile.is_nodejs is True
        assert profile.is_express is True

    @pytest.mark.asyncio
    async def test_body_content_inspected_for_signatures(self):
        # Body content must be readable via .body (not .text) — this is the
        # second half of the same attribute-name bug.
        resp = ParsedResponse(
            status=200, reason="OK", headers={},
            body="powered by django and csrftoken cookie",
        )
        profile = await TechFingerprinter().fingerprint("http://test/", _FakeClient(resp))
        assert profile.is_python is True
        assert profile.is_django is True

    @pytest.mark.asyncio
    async def test_client_exception_returns_default_profile(self):
        class RaisingClient:
            async def get(self, url, headers=None):
                raise ConnectionError("refused")

        profile = await TechFingerprinter().fingerprint("http://test/", RaisingClient())
        assert isinstance(profile, TechProfile)
        assert profile.status_code == 0
