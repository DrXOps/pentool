"""Unit-тесты для pentool/utils/copy_as.py."""

from __future__ import annotations

import pytest
from pentool.utils.parser import ParsedRequest
from pentool.utils.copy_as import (
    copy_as_curl,
    copy_as_ffuf,
    copy_as_sqlmap,
    copy_as_nmap,
    copy_as_jwt_tool,
    copy_as_fetch,
    save_request_txt,
)


@pytest.fixture
def get_req():
    return ParsedRequest(
        method="GET",
        url="http://example.com/search?q=test",
        headers={"Host": "example.com", "User-Agent": "Mozilla/5.0"},
        body="",
    )


@pytest.fixture
def post_req():
    return ParsedRequest(
        method="POST",
        url="http://example.com/login",
        headers={"Host": "example.com", "Content-Type": "application/x-www-form-urlencoded"},
        body="user=admin&pass=secret",
    )


@pytest.fixture
def jwt_req():
    return ParsedRequest(
        method="GET",
        url="http://example.com/api",
        headers={
            "Host": "example.com",
            "Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ.",
        },
        body="",
    )


class TestCopyAsCurl:
    def test_get_request(self, get_req):
        cmd = copy_as_curl(get_req)
        assert "curl" in cmd
        assert "example.com" in cmd

    def test_post_request(self, post_req):
        cmd = copy_as_curl(post_req)
        assert "-X" in cmd
        assert "POST" in cmd
        assert "--data-raw" in cmd

    def test_skips_content_length(self, post_req):
        post_req.headers["Content-Length"] = "21"
        cmd = copy_as_curl(post_req)
        assert "Content-Length" not in cmd

    def test_includes_headers(self, get_req):
        cmd = copy_as_curl(get_req)
        assert "User-Agent" in cmd


class TestCopyAsFfuf:
    def test_adds_fuzz_marker(self, get_req):
        cmd = copy_as_ffuf(get_req)
        assert "FUZZ" in cmd
        assert "ffuf" in cmd

    def test_keeps_existing_fuzz(self):
        req = ParsedRequest(
            method="GET",
            url="http://example.com/FUZZ",
            headers={"Host": "example.com"},
            body="",
        )
        cmd = copy_as_ffuf(req)
        assert cmd.count("FUZZ") >= 1

    def test_post_method(self, post_req):
        cmd = copy_as_ffuf(post_req)
        assert "-X" in cmd
        assert "POST" in cmd


class TestCopyAsSqlmap:
    def test_basic(self, post_req):
        cmd = copy_as_sqlmap(post_req)
        assert "sqlmap" in cmd
        assert "-r" in cmd
        assert "--batch" in cmd

    def test_with_body_params(self, post_req):
        cmd = copy_as_sqlmap(post_req)
        assert "--data" in cmd


class TestCopyAsNmap:
    def test_basic(self, get_req):
        cmd = copy_as_nmap(get_req)
        assert "nmap" in cmd
        assert "example.com" in cmd

    def test_https_port(self):
        req = ParsedRequest(
            method="GET",
            url="https://secure.example.com/",
            headers={"Host": "secure.example.com"},
            body="",
        )
        cmd = copy_as_nmap(req)
        assert "443" in cmd

    def test_custom_port(self):
        req = ParsedRequest(
            method="GET",
            url="http://example.com:8080/",
            headers={"Host": "example.com:8080"},
            body="",
        )
        cmd = copy_as_nmap(req)
        assert "8080" in cmd


class TestCopyAsJwtTool:
    def test_jwt_in_auth_header(self, jwt_req):
        cmd = copy_as_jwt_tool(jwt_req)
        assert "jwt_tool" in cmd
        assert "eyJ" in cmd

    def test_no_jwt(self, get_req):
        cmd = copy_as_jwt_tool(get_req)
        assert "No JWT found" in cmd

    def test_jwt_in_cookie(self):
        req = ParsedRequest(
            method="GET",
            url="http://example.com/",
            headers={
                "Host": "example.com",
                "Cookie": "token=eyJhbGciOiJub25lIn0.eyJ1c2VyIjoiYWRtaW4ifQ.",
            },
            body="",
        )
        cmd = copy_as_jwt_tool(req)
        assert "jwt_tool" in cmd

    def test_non_jwt_bearer(self):
        req = ParsedRequest(
            method="GET",
            url="http://example.com/",
            headers={"Authorization": "Bearer notajwt"},
            body="",
        )
        cmd = copy_as_jwt_tool(req)
        assert "No JWT found" in cmd


class TestCopyAsFetch:
    def test_basic_get(self, get_req):
        cmd = copy_as_fetch(get_req)
        assert "fetch(" in cmd
        assert "example.com" in cmd

    def test_post_with_body(self, post_req):
        cmd = copy_as_fetch(post_req)
        assert "POST" in cmd
        assert "body" in cmd

    def test_skips_host_header(self, get_req):
        cmd = copy_as_fetch(get_req)
        # host header should be excluded
        assert '"Host"' not in cmd


class TestSaveRequestTxt:
    def test_saves_file(self, tmp_path, post_req):
        path = str(tmp_path / "request.txt")
        save_request_txt(post_req, path)
        content = open(path).read()
        assert "POST" in content
        assert "example.com" in content
        assert "user=admin" in content

    def test_get_request(self, tmp_path, get_req):
        path = str(tmp_path / "request.txt")
        save_request_txt(get_req, path)
        content = open(path).read()
        assert "GET" in content
