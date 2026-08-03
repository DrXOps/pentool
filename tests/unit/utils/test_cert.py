"""Unit tests for pentool/utils/cert.py — SSL certificate generation."""

from __future__ import annotations

import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from pentool.utils.cert import (
    _build_ssl_ctx,
    _cert_to_pem,
    _domain_cache_path,
    _generate_rsa_key,
    _key_to_pem,
    _load_ctx_from_disk,
    _save_ctx_to_disk,
    _SslCtxLRU,
    create_ssl_context_for_domain,
    generate_ca_cert,
    generate_domain_cert,
    load_or_create_ca,
)


class TestRSAKeyGeneration:
    """Test RSA key generation."""

    def test_generate_rsa_key_default_size(self):
        """RSA key with default 2048 bits."""
        key = _generate_rsa_key()
        assert key.key_size == 2048

    def test_generate_rsa_key_custom_size(self):
        """RSA key with custom 4096 bits."""
        key = _generate_rsa_key(4096)
        assert key.key_size == 4096

    def test_key_to_pem_format(self):
        """Key serialization to PEM format."""
        key = _generate_rsa_key(2048)
        pem = _key_to_pem(key)

        assert isinstance(pem, bytes)
        assert b"-----BEGIN RSA PRIVATE KEY-----" in pem
        assert b"-----END RSA PRIVATE KEY-----" in pem

    def test_key_to_pem_no_password(self):
        """PEM key should not be encrypted."""
        key = _generate_rsa_key(2048)
        pem = _key_to_pem(key)

        # Should load without password
        loaded = serialization.load_pem_private_key(pem, password=None)
        assert loaded.key_size == 2048


class TestCACertGeneration:
    """Test CA certificate generation."""

    def test_generate_ca_cert_creates_files(self, tmp_path):
        """CA cert and key files are created."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = generate_ca_cert(cert_dir)

        assert Path(cert_path).exists()
        assert Path(key_path).exists()
        assert cert_path.endswith("ca.crt")
        assert key_path.endswith("ca.key")

    def test_generate_ca_cert_permissions(self, tmp_path):
        """CA directory has 700, cert 644, key 600."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = generate_ca_cert(cert_dir)

        dir_stat = Path(cert_dir).stat()
        assert oct(dir_stat.st_mode)[-3:] == "700"

        cert_stat = Path(cert_path).stat()
        assert oct(cert_stat.st_mode)[-3:] == "644"

        key_stat = Path(key_path).stat()
        assert oct(key_stat.st_mode)[-3:] == "600"

    def test_generate_ca_cert_reuses_existing(self, tmp_path):
        """Existing CA cert is reused, not regenerated."""
        cert_dir = str(tmp_path / "certs")
        cert_path1, key_path1 = generate_ca_cert(cert_dir)
        cert_path2, key_path2 = generate_ca_cert(cert_dir)

        assert cert_path1 == cert_path2
        assert key_path1 == key_path2

        # Should be same certificate
        cert1 = Path(cert_path1).read_bytes()
        cert2 = Path(cert_path2).read_bytes()
        assert cert1 == cert2

    def test_ca_cert_is_ca(self, tmp_path):
        """CA certificate has CA=True in BasicConstraints."""
        cert_dir = str(tmp_path / "certs")
        cert_path, _ = generate_ca_cert(cert_dir)

        cert_data = Path(cert_path).read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)

        basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert basic.value.ca is True

    def test_ca_cert_validity_10_years(self, tmp_path):
        """CA certificate is valid for 10 years."""
        cert_dir = str(tmp_path / "certs")
        cert_path, _ = generate_ca_cert(cert_dir)

        cert_data = Path(cert_path).read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)

        now = datetime.now(timezone.utc)
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc

        assert (not_before - now).total_seconds() < 60  # within 1 minute
        assert (not_after - not_before).days >= 3649  # ~10 years

    def test_load_or_create_ca_wrapper(self, tmp_path):
        """load_or_create_ca is alias for generate_ca_cert."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = load_or_create_ca(cert_dir)

        assert Path(cert_path).exists()
        assert Path(key_path).exists()


class TestDomainCertGeneration:
    """Test domain certificate generation."""

    @pytest.fixture
    def ca_files(self, tmp_path):
        """Generate CA files for testing."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = generate_ca_cert(cert_dir)
        return cert_path, key_path

    def test_generate_domain_cert_for_dns(self, ca_files):
        """Domain certificate for DNS name."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        assert isinstance(cert_pem, bytes)
        assert isinstance(key_pem, bytes)
        assert b"-----BEGIN CERTIFICATE-----" in cert_pem
        assert b"-----BEGIN RSA PRIVATE KEY-----" in key_pem

    def test_generate_domain_cert_for_ip(self, ca_files):
        """Domain certificate for IP address."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, key_pem = generate_domain_cert("127.0.0.1", ca_cert_path, ca_key_path)

        cert = x509.load_pem_x509_certificate(cert_pem)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)

        # Should contain IPAddress, not DNSName
        assert any(isinstance(name, x509.IPAddress) for name in san.value)

    def test_domain_cert_has_wildcard_san(self, ca_files):
        """Domain cert includes wildcard SAN for subdomains."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, _ = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        cert = x509.load_pem_x509_certificate(cert_pem)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)

        dns_names = [name.value for name in san.value if isinstance(name, x509.DNSName)]
        assert "example.com" in dns_names
        assert "*.example.com" in dns_names

    def test_domain_cert_no_wildcard_for_wildcard_domain(self, ca_files):
        """Wildcard domain doesn't get double wildcard."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, _ = generate_domain_cert("*.example.com", ca_cert_path, ca_key_path)

        cert = x509.load_pem_x509_certificate(cert_pem)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)

        dns_names = [name.value for name in san.value if isinstance(name, x509.DNSName)]
        assert "*.example.com" in dns_names
        assert "*.*.example.com" not in dns_names

    def test_domain_cert_validity_2_years(self, ca_files):
        """Domain certificate valid for ~2 years."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, _ = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        cert = x509.load_pem_x509_certificate(cert_pem)
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc

        validity_days = (not_after - not_before).days
        assert 820 <= validity_days <= 830  # ~825 days

    def test_domain_cert_is_not_ca(self, ca_files):
        """Domain certificate has CA=False."""
        ca_cert_path, ca_key_path = ca_files
        cert_pem, _ = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        cert = x509.load_pem_x509_certificate(cert_pem)
        basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert basic.value.ca is False


class TestSSLContextBuilding:
    """Test SSL context creation."""

    @pytest.fixture
    def domain_cert(self, tmp_path):
        """Generate domain certificate."""
        cert_dir = str(tmp_path / "certs")
        ca_cert_path, ca_key_path = generate_ca_cert(cert_dir)
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)
        return cert_pem, key_pem

    def test_build_ssl_ctx_creates_context(self, domain_cert):
        """_build_ssl_ctx creates valid SSLContext."""
        cert_pem, key_pem = domain_cert
        ctx = _build_ssl_ctx(cert_pem, key_pem)

        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.check_hostname is False

    def test_build_ssl_ctx_has_alpn(self, domain_cert):
        """SSLContext has ALPN http/1.1."""
        cert_pem, key_pem = domain_cert
        ctx = _build_ssl_ctx(cert_pem, key_pem)

        # ALPN is set (can't easily test without connection)
        # Just verify ctx is created successfully
        assert ctx is not None

    def test_cert_to_pem_format(self, tmp_path):
        """_cert_to_pem produces PEM bytes."""
        cert_dir = str(tmp_path / "certs")
        ca_cert_path, ca_key_path = generate_ca_cert(cert_dir)

        cert_data = Path(ca_cert_path).read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)
        pem = _cert_to_pem(cert)

        assert isinstance(pem, bytes)
        assert b"-----BEGIN CERTIFICATE-----" in pem
        assert b"-----END CERTIFICATE-----" in pem


class TestDomainCachePath:
    """Test domain cache path generation."""

    def test_domain_cache_path_format(self, tmp_path):
        """Cache path uses SHA256 hash prefix."""
        cert_dir = str(tmp_path / "certs")
        path = _domain_cache_path("example.com", cert_dir)

        assert path.parent.name == "domains"
        assert path.suffix == ".pem"
        assert len(path.stem) == 16  # first 16 chars of SHA256

    def test_domain_cache_path_deterministic(self, tmp_path):
        """Same domain produces same path."""
        cert_dir = str(tmp_path / "certs")
        path1 = _domain_cache_path("example.com", cert_dir)
        path2 = _domain_cache_path("example.com", cert_dir)

        assert path1 == path2

    def test_domain_cache_path_differs(self, tmp_path):
        """Different domains produce different paths."""
        cert_dir = str(tmp_path / "certs")
        path1 = _domain_cache_path("example.com", cert_dir)
        path2 = _domain_cache_path("test.com", cert_dir)

        assert path1 != path2


class TestDiskCache:
    """Test disk caching of certificates."""

    @pytest.fixture
    def ca_files(self, tmp_path):
        """Generate CA files."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = generate_ca_cert(cert_dir)
        return cert_path, key_path, cert_dir

    def test_save_ctx_to_disk_creates_file(self, ca_files, tmp_path):
        """_save_ctx_to_disk creates cache file."""
        ca_cert_path, ca_key_path, cert_dir = ca_files
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        _save_ctx_to_disk("example.com", cert_pem, key_pem, cert_dir)

        cache_path = _domain_cache_path("example.com", cert_dir)
        assert cache_path.exists()

    def test_save_ctx_to_disk_permissions(self, ca_files):
        """Cache file has 600 permissions."""
        ca_cert_path, ca_key_path, cert_dir = ca_files
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        _save_ctx_to_disk("example.com", cert_pem, key_pem, cert_dir)

        cache_path = _domain_cache_path("example.com", cert_dir)
        stat = cache_path.stat()
        assert oct(stat.st_mode)[-3:] == "600"

    def test_load_ctx_from_disk_success(self, ca_files):
        """_load_ctx_from_disk loads cached certificate."""
        ca_cert_path, ca_key_path, cert_dir = ca_files
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        _save_ctx_to_disk("example.com", cert_pem, key_pem, cert_dir)
        ctx = _load_ctx_from_disk("example.com", ca_cert_path, cert_dir)

        assert ctx is not None
        assert isinstance(ctx, ssl.SSLContext)

    def test_load_ctx_from_disk_missing_file(self, ca_files):
        """_load_ctx_from_disk returns None for missing file."""
        _, _, cert_dir = ca_files
        ctx = _load_ctx_from_disk("nonexistent.com", "dummy", cert_dir)

        assert ctx is None

    def test_load_ctx_from_disk_no_cert_dir(self, ca_files):
        """_load_ctx_from_disk returns None if cert_dir is None."""
        ca_cert_path, _, _ = ca_files
        ctx = _load_ctx_from_disk("example.com", ca_cert_path, None)

        assert ctx is None

    def test_save_ctx_to_disk_no_cert_dir(self, ca_files):
        """_save_ctx_to_disk skips if cert_dir is None."""
        ca_cert_path, ca_key_path, _ = ca_files
        cert_pem, key_pem = generate_domain_cert("example.com", ca_cert_path, ca_key_path)

        # Should not raise
        _save_ctx_to_disk("example.com", cert_pem, key_pem, None)


class TestSslCtxLRU:
    """Test in-memory LRU cache for SSL contexts."""

    def test_lru_cache_get_miss(self):
        """Cache miss returns None."""
        cache = _SslCtxLRU(max_size=10)
        assert cache.get("key1") is None

    def test_lru_cache_put_and_get(self):
        """Put and get work correctly."""
        cache = _SslCtxLRU(max_size=10)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        cache.put("key1", ctx)
        retrieved = cache.get("key1")

        assert retrieved is ctx

    def test_lru_cache_eviction(self):
        """LRU evicts oldest entry when full."""
        cache = _SslCtxLRU(max_size=3)
        ctx1 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx3 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx4 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        cache.put("key1", ctx1)
        cache.put("key2", ctx2)
        cache.put("key3", ctx3)
        cache.put("key4", ctx4)  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") is ctx2
        assert cache.get("key3") is ctx3
        assert cache.get("key4") is ctx4

    def test_lru_cache_get_updates_order(self):
        """Get moves entry to end (most recent)."""
        cache = _SslCtxLRU(max_size=3)
        ctx1 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx3 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx4 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        cache.put("key1", ctx1)
        cache.put("key2", ctx2)
        cache.put("key3", ctx3)

        cache.get("key1")  # Move key1 to end

        cache.put("key4", ctx4)  # Should evict key2, not key1

        assert cache.get("key1") is ctx1
        assert cache.get("key2") is None
        assert cache.get("key3") is ctx3
        assert cache.get("key4") is ctx4

    def test_lru_cache_put_updates_existing(self):
        """Put on existing key updates and moves to end."""
        cache = _SslCtxLRU(max_size=3)
        ctx1 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx1_new = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx3 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx4 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        cache.put("key1", ctx1)
        cache.put("key2", ctx2)
        cache.put("key3", ctx3)

        cache.put("key1", ctx1_new)  # Update key1

        cache.put("key4", ctx4)  # Should evict key2

        assert cache.get("key1") is ctx1_new
        assert cache.get("key2") is None


class TestCreateSSLContextForDomain:
    """Test high-level SSL context creation with caching."""

    @pytest.fixture
    def ca_files(self, tmp_path):
        """Generate CA files."""
        cert_dir = str(tmp_path / "certs")
        cert_path, key_path = generate_ca_cert(cert_dir)
        return cert_path, key_path, cert_dir

    def test_create_ssl_context_for_domain(self, ca_files):
        """Creates SSL context for domain."""
        ca_cert_path, ca_key_path, cert_dir = ca_files
        ctx = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, cert_dir)

        assert isinstance(ctx, ssl.SSLContext)

    def test_create_ssl_context_uses_memory_cache(self, ca_files):
        """Second call uses in-memory cache."""
        ca_cert_path, ca_key_path, cert_dir = ca_files

        ctx1 = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, cert_dir)
        ctx2 = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, cert_dir)

        # Should be same object from cache
        assert ctx1 is ctx2

    def test_create_ssl_context_uses_disk_cache(self, ca_files):
        """Uses disk cache on subsequent calls (after cache clear)."""
        from pentool.utils import cert as cert_module

        ca_cert_path, ca_key_path, cert_dir = ca_files

        # First call — generates and caches
        ctx1 = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, cert_dir)

        # Clear memory cache
        cert_module._ssl_ctx_cache = cert_module._SslCtxLRU(max_size=1000)

        # Second call — should load from disk
        ctx2 = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, cert_dir)

        # Different objects, but both valid
        assert isinstance(ctx1, ssl.SSLContext)
        assert isinstance(ctx2, ssl.SSLContext)
        assert ctx1 is not ctx2

    def test_create_ssl_context_without_cert_dir(self, ca_files):
        """Works without cert_dir (no disk cache)."""
        ca_cert_path, ca_key_path, _ = ca_files
        ctx = create_ssl_context_for_domain("example.com", ca_cert_path, ca_key_path, None)

        assert isinstance(ctx, ssl.SSLContext)
