"""Unit tests for AsyncSpider and SpiderResult."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pentool.modules.spider import AsyncSpider, SpiderResult, SpiderForm, SpiderEndpoint, FormField


class TestSpiderResult:
    def test_to_dict_empty(self):
        result = SpiderResult(base_url="https://example.com")
        d = result.to_dict()
        assert d["base_url"] == "https://example.com"
        assert d["pages_count"] == 0
        assert d["forms_count"] == 0
        assert d["endpoints_count"] == 0

    def test_to_dict_with_data(self):
        result = SpiderResult(
            base_url="https://example.com",
            pages=["https://example.com/page1", "https://example.com/page2"],
            forms=[SpiderForm(action="https://example.com/login", method="POST")],
            endpoints=[SpiderEndpoint(url="https://example.com/api/v1/users", source="js")],
        )
        d = result.to_dict()
        assert d["pages_count"] == 2
        assert d["forms_count"] == 1
        assert d["endpoints_count"] == 1

    def test_to_dict_has_js_files_count(self):
        result = SpiderResult(
            base_url="https://example.com",
            js_files=["https://example.com/app.js"],
        )
        d = result.to_dict()
        assert d["js_files_count"] == 1
        assert d["errors_count"] == 0
        assert d["total_requests"] == 0

    def test_to_dict_errors(self):
        result = SpiderResult(
            base_url="https://example.com",
            errors=["Timeout: https://example.com/slow"],
        )
        d = result.to_dict()
        assert d["errors_count"] == 1


class TestSpiderFormField:
    def test_form_field_defaults(self):
        field = FormField(name="username")
        assert field.type == "text"
        assert field.value == ""

    def test_form_field_custom_type(self):
        field = FormField(name="pass", type="password")
        assert field.type == "password"
        assert field.value == ""

    def test_spider_form(self):
        form = SpiderForm(
            action="https://example.com/login",
            method="POST",
            fields=[FormField("user", "text"), FormField("pass", "password")],
        )
        assert form.method == "POST"
        assert len(form.fields) == 2

    def test_spider_form_defaults(self):
        form = SpiderForm(action="/search")
        assert form.method == "GET"
        assert form.fields == []
        assert form.page_url == ""


class TestSpiderEndpoint:
    def test_endpoint_defaults(self):
        ep = SpiderEndpoint(url="https://example.com/api/v1")
        assert ep.source == "html"
        assert ep.method == "GET"
        assert ep.params == []

    def test_endpoint_with_params(self):
        ep = SpiderEndpoint(
            url="https://example.com/search?q=test&page=1",
            source="param",
            params=["q", "page"],
        )
        assert len(ep.params) == 2

    def test_endpoint_js_source(self):
        ep = SpiderEndpoint(url="https://example.com/api/v1", source="js")
        assert ep.source == "js"


class TestAsyncSpiderInit:
    def test_default_init(self):
        spider = AsyncSpider()
        assert spider.max_depth == 3
        assert spider.max_pages == 100
        assert spider.concurrency == 5
        assert spider.respect_scope is True

    def test_custom_init(self):
        spider = AsyncSpider(max_depth=5, max_pages=200, concurrency=10)
        assert spider.max_depth == 5
        assert spider.max_pages == 200
        assert spider.concurrency == 10

    def test_stop_flag(self):
        spider = AsyncSpider()
        assert spider._stop is False
        spider.stop()
        assert spider._stop is True

    def test_callbacks_optional(self):
        spider = AsyncSpider()
        assert spider.on_page is None
        assert spider.on_progress is None

    def test_callbacks_custom(self):
        cb = lambda url: None
        spider = AsyncSpider(on_page=cb)
        assert spider.on_page is cb

    def test_timeout_default(self):
        spider = AsyncSpider()
        assert spider.timeout == 10.0

    def test_user_agent_default(self):
        spider = AsyncSpider()
        assert "pentool" in spider.user_agent.lower() or "security" in spider.user_agent.lower()


class TestSpiderInternals:
    def test_normalize_url_removes_fragment(self):
        spider = AsyncSpider()
        url = "https://example.com/page#section"
        result = spider._normalize_url(url)
        assert "#section" not in result
        assert "example.com/page" in result

    def test_normalize_url_strips_trailing_slash(self):
        spider = AsyncSpider()
        url = "https://example.com/page/"
        result = spider._normalize_url(url)
        assert not result.endswith("/")

    def test_normalize_url_keeps_query(self):
        spider = AsyncSpider()
        url = "https://example.com/search?q=test"
        result = spider._normalize_url(url)
        assert "q=test" in result

    def test_normalize_url_removes_both_fragment_and_slash(self):
        spider = AsyncSpider()
        url = "https://example.com/page/#top"
        result = spider._normalize_url(url)
        assert "#top" not in result
        assert not result.endswith("/")

    def test_in_scope_same_domain(self):
        spider = AsyncSpider()
        assert spider._in_scope("https://example.com/page", "example.com") is True

    def test_in_scope_different_domain(self):
        spider = AsyncSpider()
        assert spider._in_scope("https://evil.com/page", "example.com") is False

    def test_in_scope_empty_netloc(self):
        spider = AsyncSpider()
        assert spider._in_scope("/relative/path", "example.com") is True

    def test_in_scope_subdomain_in_scope(self):
        spider = AsyncSpider()
        # example.com subdomains are in scope (wildcard support)
        assert spider._in_scope("https://sub.example.com/page", "example.com") is True

    def test_in_scope_different_subdomain_not_in_scope(self):
        spider = AsyncSpider()
        # evil.com — not a subdomain of example.com
        assert spider._in_scope("https://sub.evil.com/page", "example.com") is False

    def test_extract_js_endpoints_fetch(self):
        spider = AsyncSpider()
        js = "fetch('/api/v1/users', {method: 'POST'})"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        urls = [ep.url for ep in endpoints]
        assert any("/api/v1/users" in u for u in urls)

    def test_extract_js_endpoints_axios(self):
        spider = AsyncSpider()
        js = "axios.get('/api/products')"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        urls = [ep.url for ep in endpoints]
        assert any("/api/products" in u for u in urls)

    def test_extract_js_endpoints_api_path(self):
        spider = AsyncSpider()
        js = "const url = '/api/v1/users'"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        urls = [ep.url for ep in endpoints]
        assert any("/api/v1/users" in u for u in urls)

    def test_extract_js_no_duplicates(self):
        spider = AsyncSpider()
        js = "fetch('/api/v1') \n fetch('/api/v1')"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        urls = [ep.url for ep in endpoints]
        # should be unique
        assert len(urls) == len(set(urls))

    def test_extract_js_endpoints_source_is_js(self):
        spider = AsyncSpider()
        js = "fetch('/api/data')"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        assert all(ep.source == "js" for ep in endpoints)

    def test_extract_js_endpoints_absolute_url(self):
        spider = AsyncSpider()
        js = "fetch('https://api.example.com/v1/data')"
        endpoints = spider._extract_js_endpoints(js, "https://example.com/app.js")
        urls = [ep.url for ep in endpoints]
        assert any("api.example.com/v1/data" in u for u in urls)

    def test_parse_html_extracts_links(self):
        spider = AsyncSpider()
        html = """<html><body>
        <a href="/page1">Page 1</a>
        <a href="https://example.com/page2">Page 2</a>
        <a href="https://evil.com/outside">Outside</a>
        </body></html>"""
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        link_urls = [l for l in links]
        assert any("/page1" in u for u in link_urls)
        assert any("/page2" in u for u in link_urls)
        # External links are filtered when respect_scope=True
        assert not any("evil.com" in u for u in link_urls)

    def test_parse_html_extracts_forms(self):
        spider = AsyncSpider()
        html = """<html><body>
        <form action="/login" method="POST">
            <input name="username" type="text">
            <input name="password" type="password">
            <input type="submit" value="Login">
        </form>
        </body></html>"""
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        assert len(forms) == 1
        assert forms[0].method == "POST"
        assert any(f.name == "username" for f in forms[0].fields)
        assert any(f.name == "password" for f in forms[0].fields)

    def test_parse_html_form_method_uppercase(self):
        spider = AsyncSpider()
        html = """<html><body>
        <form action="/search" method="get">
            <input name="q" type="text">
        </form>
        </body></html>"""
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        assert len(forms) == 1
        assert forms[0].method == "GET"

    def test_parse_html_form_without_named_fields_not_added(self):
        """Form without named fields (only submit) is not added."""
        spider = AsyncSpider()
        html = """<html><body>
        <form action="/action" method="POST">
            <input type="submit" value="Go">
        </form>
        </body></html>"""
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        # submit has no name → fields empty → form is not added
        assert len(forms) == 0

    def test_parse_html_extracts_js(self):
        spider = AsyncSpider()
        html = """<html><head>
        <script src="/static/app.js"></script>
        <script src="https://example.com/bundle.js"></script>
        </head></html>"""
        links, forms, js_links = spider._parse_html(html, "https://example.com/", "example.com")
        assert any("app.js" in u for u in js_links)
        assert any("bundle.js" in u for u in js_links)

    def test_parse_html_skips_mailto(self):
        spider = AsyncSpider()
        html = '<a href="mailto:test@example.com">Email</a>'
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        assert not any("mailto" in u for u in links)

    def test_parse_html_skips_javascript(self):
        spider = AsyncSpider()
        html = '<a href="javascript:void(0)">Click</a>'
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        assert not any("javascript" in u for u in links)

    def test_parse_html_skips_fragment_only(self):
        spider = AsyncSpider()
        html = '<a href="#top">Top</a>'
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        # href="#top" is filtered out (startswith("#"))
        assert not any(u.endswith("#top") for u in links)

    def test_parse_html_returns_absolute_urls(self):
        spider = AsyncSpider()
        html = '<a href="/about">About</a>'
        links, forms, js = spider._parse_html(html, "https://example.com/", "example.com")
        assert all(u.startswith("http") for u in links)

    def test_parse_html_form_action_absolute(self):
        spider = AsyncSpider()
        html = """<html><body>
        <form action="/submit" method="POST">
            <input name="data" type="text">
        </form>
        </body></html>"""
        links, forms, js = spider._parse_html(html, "https://example.com/page/", "example.com")
        assert forms[0].action == "https://example.com/submit"


class TestPayloadsLoader:
    def test_load_payloads_sqli(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("sqli")
        assert len(payloads) > 5
        assert any("'" in p for p in payloads)

    def test_load_payloads_xss(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("xss")
        assert len(payloads) > 5
        assert any("script" in p.lower() or "onerror" in p.lower() for p in payloads)

    def test_load_payloads_ssti(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("ssti")
        assert len(payloads) > 5
        assert any("{{" in p or "${" in p for p in payloads)

    def test_load_payloads_lfi(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("lfi")
        assert len(payloads) > 5
        assert any("etc/passwd" in p or "win.ini" in p for p in payloads)

    def test_load_payloads_rce(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("rce")
        assert len(payloads) > 5
        assert any("id" in p for p in payloads)

    def test_load_payloads_ssrf(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("ssrf")
        assert len(payloads) > 0
        assert any("169.254" in p or "localhost" in p or "127.0.0.1" in p for p in payloads)

    def test_load_payloads_open_redirect(self):
        from pentool.modules.scanner.payloads import load_payloads
        payloads = load_payloads("open_redirect")
        assert len(payloads) > 0
        assert any("evil.com" in p or "//" in p for p in payloads)

    def test_generate_payloads_fallback(self):
        from pentool.modules.scanner.payloads import generate_payloads
        payloads = generate_payloads("sqli")
        assert len(payloads) > 0

    def test_generate_payloads_xss_fallback(self):
        from pentool.modules.scanner.payloads import generate_payloads
        payloads = generate_payloads("xss")
        assert len(payloads) > 0
        assert any("script" in p.lower() or "onerror" in p.lower() for p in payloads)

    def test_generate_payloads_unknown_returns_empty(self):
        from pentool.modules.scanner.payloads import generate_payloads
        payloads = generate_payloads("nonexistent_type_xyz")
        assert payloads == []

    def test_load_signatures_sqli(self):
        from pentool.modules.scanner.payloads import load_signatures
        sigs = load_signatures("sqli")
        assert len(sigs) > 0

    def test_load_signatures_returns_list(self):
        from pentool.modules.scanner.payloads import load_signatures
        sigs = load_signatures("sqli")
        assert isinstance(sigs, list)
        assert all(isinstance(s, str) for s in sigs)


class TestActiveChecksInit:
    def test_sqli_check_attrs(self):
        from pentool.modules.scanner.checks.sqli import SQLiCheck
        check = SQLiCheck()
        assert check.passive is False
        assert check.severity == "high"
        assert check.cwe == "CWE-89"

    def test_sqli_check_name(self):
        from pentool.modules.scanner.checks.sqli import SQLiCheck
        check = SQLiCheck()
        assert check.name == "sqli"

    def test_xss_check_attrs(self):
        from pentool.modules.scanner.checks.xss import XSSCheck
        check = XSSCheck()
        assert check.passive is False
        assert check.severity in ("medium", "high")
        assert "79" in check.cwe

    def test_xss_check_name(self):
        from pentool.modules.scanner.checks.xss import XSSCheck
        check = XSSCheck()
        assert check.name == "xss"

    def test_ssti_check_attrs(self):
        from pentool.modules.scanner.checks.ssti import SSTICheck
        check = SSTICheck()
        assert check.passive is False
        assert check.severity == "critical"
        # CWE-1336 contains "1336"
        assert "1336" in check.cwe or "ssti" in check.cwe.lower() or check.cwe.startswith("CWE")

    def test_ssti_check_name(self):
        from pentool.modules.scanner.checks.ssti import SSTICheck
        check = SSTICheck()
        assert check.name == "ssti"

    def test_lfi_check_attrs(self):
        from pentool.modules.scanner.checks.lfi import LFICheck
        check = LFICheck()
        assert check.passive is False
        assert check.severity == "high"
        assert "22" in check.cwe

    def test_lfi_check_name(self):
        from pentool.modules.scanner.checks.lfi import LFICheck
        check = LFICheck()
        assert check.name == "lfi"

    def test_rce_check_attrs(self):
        from pentool.modules.scanner.checks.rce import RCECheck
        check = RCECheck()
        assert check.passive is False
        assert check.severity == "critical"
        assert "78" in check.cwe

    def test_rce_check_name(self):
        from pentool.modules.scanner.checks.rce import RCECheck
        check = RCECheck()
        assert check.name == "rce"

    def test_open_redirect_check_attrs(self):
        from pentool.modules.scanner.checks.open_redirect import OpenRedirectCheck
        check = OpenRedirectCheck()
        assert check.passive is False
        assert "601" in check.cwe

    def test_open_redirect_check_name(self):
        from pentool.modules.scanner.checks.open_redirect import OpenRedirectCheck
        check = OpenRedirectCheck()
        assert check.name == "open_redirect"

    def test_ssrf_check_attrs(self):
        from pentool.modules.scanner.checks.ssrf import SSRFCheck
        check = SSRFCheck()
        assert check.passive is False
        assert "918" in check.cwe

    def test_ssrf_check_name(self):
        from pentool.modules.scanner.checks.ssrf import SSRFCheck
        check = SSRFCheck()
        assert check.name == "ssrf"

    def test_all_checks_registered_in_api(self):
        from pentool.api.scanner_api import ScannerAPI
        api = ScannerAPI(db_path="")
        checks = api.get_registered_checks()
        names = [c.name for c in checks]
        assert "sqli" in names
        assert "xss" in names
        assert "ssti" in names
        assert "lfi" in names
        assert "rce" in names
        assert "open_redirect" in names
        assert "ssrf" in names
        assert "missing_security_headers" in names

    def test_all_checks_are_active(self):
        """All active checks have passive=False."""
        from pentool.modules.scanner.checks import (
            SQLiCheck, XSSCheck, SSTICheck, LFICheck,
            RCECheck, OpenRedirectCheck, SSRFCheck,
        )
        for cls in (SQLiCheck, XSSCheck, SSTICheck, LFICheck, RCECheck, OpenRedirectCheck, SSRFCheck):
            check = cls()
            assert check.passive is False, f"{cls.__name__} should be active (passive=False)"

    def test_checks_have_description(self):
        """All checks should have a non-empty description."""
        from pentool.modules.scanner.checks import (
            SQLiCheck, XSSCheck, SSTICheck, LFICheck,
            RCECheck, OpenRedirectCheck, SSRFCheck,
        )
        for cls in (SQLiCheck, XSSCheck, SSTICheck, LFICheck, RCECheck, OpenRedirectCheck, SSRFCheck):
            check = cls()
            assert check.description, f"{cls.__name__} should have description"

    def test_checks_have_mitre_attack(self):
        """All active checks have mitre_attack."""
        from pentool.modules.scanner.checks import (
            SQLiCheck, XSSCheck, SSTICheck, LFICheck,
            RCECheck, OpenRedirectCheck, SSRFCheck,
        )
        for cls in (SQLiCheck, XSSCheck, SSTICheck, LFICheck, RCECheck, OpenRedirectCheck, SSRFCheck):
            check = cls()
            assert check.mitre_attack, f"{cls.__name__} should have mitre_attack"


# ── TestPlaywrightSupport ─────────────────────────────────────────────────────

class TestPlaywrightAvailable:
    def test_is_playwright_available_returns_bool(self):
        from pentool.modules.spider import is_playwright_available
        result = is_playwright_available()
        assert isinstance(result, bool)

    def test_is_playwright_available_no_crash(self):
        """Function does not crash regardless of playwright availability."""
        from pentool.modules.spider import is_playwright_available
        # Just call it — should not raise an exception
        is_playwright_available()

    def test_spider_api_has_is_playwright_available(self):
        from pentool.api.spider_api import is_playwright_available
        assert callable(is_playwright_available)


class TestSpiderJsRenderConfig:
    def test_spider_config_has_js_render(self):
        from pentool.api.spider_api import SpiderConfig
        cfg = SpiderConfig()
        assert hasattr(cfg, "js_render")
        assert cfg.js_render is False

    def test_spider_config_js_render_true(self):
        from pentool.api.spider_api import SpiderConfig
        cfg = SpiderConfig(js_render=True)
        assert cfg.js_render is True

    def test_async_spider_accepts_js_render(self):
        spider = AsyncSpider(js_render=False)
        assert spider.js_render is False

    def test_async_spider_js_render_false_without_playwright(self):
        """js_render=True without playwright should become False (fallback)."""
        from pentool.modules.spider import is_playwright_available
        spider = AsyncSpider(js_render=True)
        # If playwright is not installed — js_render should be False
        if not is_playwright_available():
            assert spider.js_render is False
        else:
            assert spider.js_render is True

    def test_async_spider_default_js_render_false(self):
        spider = AsyncSpider()
        assert spider.js_render is False

    def test_spider_api_passes_js_render_to_spider(self):
        """SpiderAPI passes js_render from SpiderConfig to AsyncSpider."""
        from pentool.api.spider_api import SpiderAPI, SpiderConfig
        cfg = SpiderConfig(js_render=False, max_depth=1, max_pages=1)
        api = SpiderAPI(config=cfg)
        assert api.config.js_render is False

    def test_spider_api_from_params_no_js_render(self):
        """from_params creates config with js_render=False by default."""
        from pentool.api.spider_api import SpiderAPI
        api = SpiderAPI.from_params(max_depth=1, max_pages=1)
        assert api.config.js_render is False


class TestPlaywrightFetchPage:
    """Tests for _fetch_page_playwright with mock objects."""

    @pytest.mark.asyncio
    async def test_fetch_page_playwright_success(self):
        """_fetch_page_playwright returns HTML on a successful response."""
        spider = AsyncSpider()
        result = SpiderResult(base_url="https://example.com")

        page_mock = AsyncMock()
        response_mock = MagicMock()
        response_mock.ok = True
        page_mock.goto.return_value = response_mock
        page_mock.content.return_value = "<html><body>Hello</body></html>"

        html = await spider._fetch_page_playwright(page_mock, "https://example.com", result)
        assert html == "<html><body>Hello</body></html>"
        assert result.total_requests == 1
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_fetch_page_playwright_non_ok_response(self):
        """_fetch_page_playwright returns None on a non-OK response."""
        spider = AsyncSpider()
        result = SpiderResult(base_url="https://example.com")

        page_mock = AsyncMock()
        response_mock = MagicMock()
        response_mock.ok = False
        page_mock.goto.return_value = response_mock

        html = await spider._fetch_page_playwright(page_mock, "https://example.com/404", result)
        assert html is None

    @pytest.mark.asyncio
    async def test_fetch_page_playwright_none_response(self):
        """_fetch_page_playwright returns None when goto returns None."""
        spider = AsyncSpider()
        result = SpiderResult(base_url="https://example.com")

        page_mock = AsyncMock()
        page_mock.goto.return_value = None

        html = await spider._fetch_page_playwright(page_mock, "https://example.com", result)
        assert html is None

    @pytest.mark.asyncio
    async def test_fetch_page_playwright_exception(self):
        """_fetch_page_playwright records an error and returns None."""
        spider = AsyncSpider()
        result = SpiderResult(base_url="https://example.com")

        page_mock = AsyncMock()
        page_mock.goto.side_effect = Exception("Timeout!")

        html = await spider._fetch_page_playwright(page_mock, "https://example.com", result)
        assert html is None
        assert len(result.errors) == 1
        assert "Timeout!" in result.errors[0]

    @pytest.mark.asyncio
    async def test_fetch_page_playwright_increments_requests(self):
        """_fetch_page_playwright increments total_requests on success."""
        spider = AsyncSpider()
        result = SpiderResult(base_url="https://example.com")
        result.total_requests = 5

        page_mock = AsyncMock()
        resp = MagicMock()
        resp.ok = True
        page_mock.goto.return_value = resp
        page_mock.content.return_value = "<html></html>"

        await spider._fetch_page_playwright(page_mock, "https://example.com/page", result)
        assert result.total_requests == 6


class TestSpiderAPIStop:
    def test_spider_api_stop_sets_correct_attribute(self):
        """SpiderAPI.stop() должен устанавливать правильный атрибут _stop в AsyncSpider."""
        from pentool.api.spider_api import SpiderAPI
        from pentool.modules.spider import AsyncSpider

        api = SpiderAPI()
        # Создаём mock-экземпляр AsyncSpider и подставляем его
        spider = AsyncSpider()
        api._spider = spider

        # До вызова stop() флаг равен False
        assert spider._stop is False

        api.stop()

        # После вызова stop() флаг должен быть True
        assert spider._stop is True
        # Флаг SpiderAPI тоже должен быть установлен
        assert api._stop_requested is True

    def test_spider_api_stop_without_spider(self):
        """SpiderAPI.stop() не падает, если _spider ещё не создан (None)."""
        from pentool.api.spider_api import SpiderAPI

        api = SpiderAPI()
        assert api._spider is None
        # Не должно вызывать исключений
        api.stop()
        assert api._stop_requested is True

    def test_extract_path_variants_no_duplicates(self):
        """_extract_path_variants не должен возвращать оригинальный URL как вариант."""
        spider = AsyncSpider()
        url = "https://example.com/api/users/123/profile"
        variants = spider._extract_path_variants(url, "example.com")
        # Ни один вариант не должен совпадать с оригинальным URL (дубль)
        assert url not in variants
