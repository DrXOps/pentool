"""TLS certificate generation and management for HTTPS proxy interception."""

from __future__ import annotations

import ipaddress
import os
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.x509 import Certificate
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _generate_rsa_key(key_size: int = 2048) -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def _key_to_pem(key: RSAPrivateKey) -> bytes:
    """Serialize a private key to PEM without a password."""
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _cert_to_pem(cert: Certificate) -> bytes:
    """Serialize a certificate to PEM."""
    return cert.public_bytes(serialization.Encoding.PEM)


def generate_ca_cert(cert_dir: str) -> tuple[str, str]:
    dir_path = Path(cert_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    # Set permissions 700 for the certificate directory
    dir_path.chmod(0o700)

    cert_path = dir_path / "ca.crt"
    key_path = dir_path / "ca.key"

    if cert_path.exists() and key_path.exists():
        return str(cert_path), str(key_path)

    key = _generate_rsa_key(4096)
    now = datetime.now(timezone.utc)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Pentool CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Pentool"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Security Testing"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))  # 10 years
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(_cert_to_pem(cert))
    cert_path.chmod(0o644)

    key_path.write_bytes(_key_to_pem(key))
    key_path.chmod(0o600)

    return str(cert_path), str(key_path)


def load_or_create_ca(cert_dir: str) -> tuple[str, str]:
    return generate_ca_cert(cert_dir)


def generate_domain_cert(
    domain: str,
    ca_cert_path: str,
    ca_key_path: str,
) -> tuple[bytes, bytes]:
    # Load CA
    ca_cert = x509.load_pem_x509_certificate(Path(ca_cert_path).read_bytes())
    ca_key_data = Path(ca_key_path).read_bytes()
    ca_key = serialization.load_pem_private_key(ca_key_data, password=None)

    key = _generate_rsa_key(2048)
    now = datetime.now(timezone.utc)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
    ])

    # Determine SAN: IP or DNS
    san_list: list[x509.GeneralName] = []
    try:
        san_list.append(x509.IPAddress(ipaddress.ip_address(domain)))
    except ValueError:
        san_list.append(x509.DNSName(domain))
        # Add wildcard for subdomains
        if "." in domain and not domain.startswith("*."):
            san_list.append(x509.DNSName(f"*.{domain}"))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=825))  # ~2 years 3 months
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    return _cert_to_pem(cert), _key_to_pem(key)


def create_ssl_context_for_domain(
    domain: str,
    ca_cert_path: str,
    ca_key_path: str,
    cert_dir: str | None = None,
) -> ssl.SSLContext:
    # ── Level 1: in-memory LRU ────────────────────────────────────────────────
    cache_key = f"{domain}:{ca_cert_path}"
    ctx = _ssl_ctx_cache.get(cache_key)
    if ctx is not None:
        return ctx

    # ── Level 2: disk-cache ───────────────────────────────────────────────────
    ctx = _load_ctx_from_disk(domain, ca_cert_path, cert_dir)
    if ctx is not None:
        _ssl_ctx_cache.put(cache_key, ctx)
        return ctx

    # ── Generate new certificate ──────────────────────────────────────────────
    cert_pem, key_pem = generate_domain_cert(domain, ca_cert_path, ca_key_path)

    # Save to disk (if cert_dir is set)
    _save_ctx_to_disk(domain, cert_pem, key_pem, cert_dir)

    ctx = _build_ssl_ctx(cert_pem, key_pem)
    _ssl_ctx_cache.put(cache_key, ctx)
    return ctx


# ── Helper functions for disk-cache ──────────────────────────────────────────

def _domain_cache_path(domain: str, cert_dir: str) -> Path:
    """Path to cache file for a domain: {cert_dir}/domains/{sha256(domain)[:16]}.pem"""
    import hashlib
    key = hashlib.sha256(domain.encode()).hexdigest()[:16]
    return Path(cert_dir) / "domains" / f"{key}.pem"


def _load_ctx_from_disk(
    domain: str, ca_cert_path: str, cert_dir: str | None
) -> ssl.SSLContext | None:
    """Try to load a certificate from disk-cache.

    Checks:
    - file exists
    - certificate CN matches the domain
    - certificate does not expire within the next 30 days
    """
    if not cert_dir:
        return None
    path = _domain_cache_path(domain, cert_dir)
    if not path.exists():
        return None
    try:
        pem_data = path.read_bytes()
        # File contains cert_pem + key_pem separated by a marker
        sep = b"-----BEGIN RSA PRIVATE KEY-----"
        sep2 = b"-----BEGIN PRIVATE KEY-----"
        if sep in pem_data:
            cert_pem, key_pem = pem_data.split(sep, 1)
            key_pem = sep + key_pem
        elif sep2 in pem_data:
            cert_pem, key_pem = pem_data.split(sep2, 1)
            key_pem = sep2 + key_pem
        else:
            return None

        # Check expiry
        cert = x509.load_pem_x509_certificate(cert_pem)
        expires = cert.not_valid_after_utc
        margin = timedelta(days=30)
        if expires - datetime.now(timezone.utc) < margin:
            path.unlink(missing_ok=True)
            return None

        return _build_ssl_ctx(cert_pem, key_pem)
    except Exception:
        # Corrupted cache — delete and regenerate
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _save_ctx_to_disk(
    domain: str, cert_pem: bytes, key_pem: bytes, cert_dir: str | None
) -> None:
    if not cert_dir:
        return
    try:
        path = _domain_cache_path(domain, cert_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cert_pem + key_pem)
        path.chmod(0o600)
    except Exception:
        pass  # disk-cache is not critical — continue without it


def _build_ssl_ctx(cert_pem: bytes, key_pem: bytes) -> ssl.SSLContext:
    """Build an SSLContext from PEM bytes via temporary files."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.check_hostname = False
    ctx.set_alpn_protocols(["http/1.1"])

    with tempfile.NamedTemporaryFile(delete=False, suffix=".crt") as cf:
        cf.write(cert_pem)
        cert_tmp = cf.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".key") as kf:
        kf.write(key_pem)
        key_tmp = kf.name

    try:
        ctx.load_cert_chain(cert_tmp, key_tmp)
    finally:
        os.unlink(cert_tmp)
        os.unlink(key_tmp)

    return ctx


# ── In-memory LRU cache for SSL contexts (1000 domains) ──────────────────────

class _SslCtxLRU:
    """Simple LRU cache for SSLContext objects.

    Key — string "{domain}:{ca_cert_path}", value — ssl.SSLContext.
    Maximum 1000 entries — approximately 1–2 MB of memory.
    """
    def __init__(self, max_size: int = 1000) -> None:
        from collections import OrderedDict
        self._data: "OrderedDict[str, ssl.SSLContext]" = OrderedDict()
        self._max = max_size

    def get(self, key: str) -> ssl.SSLContext | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: str, ctx: ssl.SSLContext) -> None:
        if key in self._data:
            self._data.move_to_end(key)
            self._data[key] = ctx
            return
        self._data[key] = ctx
        if len(self._data) > self._max:
            self._data.popitem(last=False)


_ssl_ctx_cache = _SslCtxLRU(max_size=1000)
