"""Unit-тесты для pentool/modules/scanner/oob.py."""

from __future__ import annotations

import pytest

from pentool.modules.scanner.oob import OOBHelper, get_oob_helper


class TestOOBHelperEnabled:
    def test_enabled_with_url(self):
        oob = OOBHelper("https://xxx.oastify.com")
        assert oob.enabled is True

    def test_disabled_without_url(self):
        oob = OOBHelper("")
        assert oob.enabled is False

    def test_disabled_with_none_like(self):
        oob = OOBHelper()
        assert oob.enabled is False


class TestOOBHelperGeneratePayload:
    def test_generate_payload_returns_tuple(self):
        oob = OOBHelper("https://xxx.oastify.com")
        uid, url = oob.generate_payload()
        assert isinstance(uid, str)
        assert isinstance(url, str)

    def test_generate_payload_uid_in_url(self):
        oob = OOBHelper("https://xxx.oastify.com")
        uid, url = oob.generate_payload()
        assert uid in url

    def test_generate_payload_with_prefix(self):
        oob = OOBHelper("https://xxx.oastify.com")
        uid, url = oob.generate_payload(prefix="ssrf")
        assert "ssrf" in url

    def test_generate_payload_unique_each_time(self):
        oob = OOBHelper("https://xxx.oastify.com")
        uid1, url1 = oob.generate_payload()
        uid2, url2 = oob.generate_payload()
        assert uid1 != uid2
        assert url1 != url2

    def test_generate_payload_contains_base_domain(self):
        oob = OOBHelper("https://xxx.oastify.com")
        uid, url = oob.generate_payload()
        assert "oastify.com" in url

    def test_generate_payload_http_protocol(self):
        oob = OOBHelper("http://interact.sh")
        uid, url = oob.generate_payload()
        assert "interact.sh" in url
        assert uid in url


class TestOOBHelperSSRFPayloads:
    def test_ssrf_payloads_when_enabled(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_ssrf_payloads()
        assert len(payloads) > 0
        assert all(isinstance(p, str) for p in payloads)

    def test_ssrf_payloads_empty_when_disabled(self):
        oob = OOBHelper("")
        assert oob.get_ssrf_payloads() == []

    def test_ssrf_payloads_contain_oastify_domain(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_ssrf_payloads()
        assert any("oastify.com" in p for p in payloads)

    def test_ssrf_payloads_are_urls(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_ssrf_payloads()
        # Хотя бы один должен быть полноценным URL
        assert any(p.startswith("http") for p in payloads)


class TestOOBHelperRCEPayloads:
    def test_rce_payloads_when_enabled(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_rce_payloads()
        assert len(payloads) > 0

    def test_rce_payloads_empty_when_disabled(self):
        oob = OOBHelper("")
        assert oob.get_rce_payloads() == []

    def test_rce_payloads_contain_curl_or_nslookup(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_rce_payloads()
        combined = " ".join(payloads)
        assert "curl" in combined or "nslookup" in combined or "ping" in combined

    def test_rce_payloads_contain_domain(self):
        oob = OOBHelper("https://xxx.oastify.com")
        payloads = oob.get_rce_payloads()
        combined = " ".join(payloads)
        assert "oastify.com" in combined


class TestOOBHelperCheckInteractions:
    @pytest.mark.asyncio
    async def test_check_interactions_returns_list(self):
        oob = OOBHelper("https://xxx.oastify.com")
        result = await oob.check_interactions()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_check_interactions_empty_stub(self):
        # Заглушка всегда возвращает []
        oob = OOBHelper("https://xxx.oastify.com")
        result = await oob.check_interactions()
        assert result == []


class TestGetOOBHelper:
    def test_get_oob_helper_returns_oob_helper(self):
        from pentool.core.config import Config, set_config
        cfg = Config(collaborator_url="https://test.oastify.com")
        set_config(cfg)
        oob = get_oob_helper()
        assert isinstance(oob, OOBHelper)
        assert oob.enabled

    def test_get_oob_helper_disabled_when_no_url(self):
        from pentool.core.config import Config, set_config
        cfg = Config(collaborator_url="")
        set_config(cfg)
        oob = get_oob_helper()
        assert not oob.enabled

    def test_get_oob_helper_no_crash_on_config_error(self):
        """Если конфиг недоступен — возвращает отключённый хелпер."""
        oob = get_oob_helper()
        assert isinstance(oob, OOBHelper)
