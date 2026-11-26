"""A scheme-less target must become a real URL (tech-debt N2).

`pentool --smart telemetry.lightpanda.io:443` produced no history entry and one odd
`POST /v2`: the target reached Lightpanda without a scheme, so the fetch did something else
than the user asked. One helper is used by the browser command, the HTTP fallback and Target
seeding, so the interpretation cannot differ between them.
"""

from __future__ import annotations

import pytest

from pentool.utils.urls import normalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("telemetry.lightpanda.io:443", "https://telemetry.lightpanda.io:443/"),
        ("example.com", "https://example.com"),
        ("example.com/login?a=1", "https://example.com/login?a=1"),
        ("http://x.test:8080/a", "http://x.test:8080/a"),
        ("https://y.test", "https://y.test"),
        ("//z.test/q", "https://z.test/q"),
        ("  127.0.0.1:8080/  ", "https://127.0.0.1:8080/"),
    ],
)
def test_targets_get_a_scheme(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_empty_target_stays_empty() -> None:
    assert normalize_url("") == ""
    assert normalize_url("   ") == ""
