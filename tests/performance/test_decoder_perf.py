"""Performance: Decoder operations throughput."""
from __future__ import annotations

import time

import pytest

from pentool.modules.decoder import encode_op, run_chain


@pytest.mark.performance
def test_base64_encode_perf():
    # 100KB данных
    data = "A" * (100 * 1024)
    start = time.monotonic()
    for _ in range(100):
        encode_op("Base64 Encode", data)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"base64 encode 100KB x100 took {elapsed:.3f}s (limit 1.0s)"


@pytest.mark.performance
def test_url_encode_perf():
    data = "hello world <script>alert(1)</script> &param=value" * 20  # ~1KB
    start = time.monotonic()
    for _ in range(1000):
        encode_op("URL Encode", data)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"url_encode 1KB x1000 took {elapsed:.3f}s (limit 1.0s)"


@pytest.mark.performance
def test_decode_chain_perf():
    # Цепочка: base64 → url
    chain = ["Base64 Encode", "URL Encode"]
    data = "Hello, World! Test data for chain encoding performance."
    start = time.monotonic()
    for _ in range(500):
        run_chain(chain, data)
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"chain (base64→url) x500 took {elapsed:.3f}s (limit 2.0s)"
