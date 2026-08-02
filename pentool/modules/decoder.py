"""Decoder/Encoder — 15 encode/decode operations + hashing."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable

__all__ = [
    "OPERATIONS",
    "decode_smart",
    "encode_op",
    "decode_op",
    "run_chain",
    "DecoderChain",
]

# ── Operations registry ────────────────────────────────────────────────────────

def _url_encode(s: str) -> str:
    return urllib.parse.quote(s, safe="")

def _url_decode(s: str) -> str:
    return urllib.parse.unquote(s)

def _base64_encode(s: str) -> str:
    return base64.b64encode(s.encode()).decode()

def _base64_decode(s: str) -> str:
    # Add padding if needed
    padded = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.b64decode(padded).decode("utf-8", errors="replace")

def _base64url_encode(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")

def _base64url_decode(s: str) -> str:
    padded = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")

def _html_encode(s: str) -> str:
    return html.escape(s, quote=True)

def _html_decode(s: str) -> str:
    return html.unescape(s)

def _hex_encode(s: str) -> str:
    return s.encode().hex()

def _hex_decode(s: str) -> str:
    # Remove separators
    clean = re.sub(r"[\s:%-]", "", s)
    # Keep only hex characters
    hex_only = re.sub(r"[^0-9a-fA-F]", "", clean)
    if not hex_only:
        return s  # not hex — return as is
    # Align to even length
    if len(hex_only) % 2:
        hex_only = "0" + hex_only
    return bytes.fromhex(hex_only).decode("utf-8", errors="replace")

def _unicode_encode(s: str) -> str:
    result = ""
    for ch in s:
        cp = ord(ch)
        if cp > 127:
            result += f"\\u{cp:04x}"
        else:
            result += ch
    return result

def _unicode_decode(s: str) -> str:
    try:
        return s.encode("raw_unicode_escape").decode("unicode_escape")
    except Exception:
        return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)

def _jwt_decode(s: str) -> str:
    """Decode JWT header + payload without signature verification."""
    parts = s.strip().split(".")
    if len(parts) < 2:
        return "Invalid JWT"
    result = {}
    for i, name in enumerate(("header", "payload")):
        try:
            part = parts[i]
            padded = part + "=" * (4 - len(part) % 4) if len(part) % 4 else part
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
            result[name] = json.loads(decoded)
        except Exception as exc:
            result[name] = f"[error: {exc}]"
    return json.dumps(result, indent=2, ensure_ascii=False)

def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()

def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def _sha512(s: str) -> str:
    return hashlib.sha512(s.encode()).hexdigest()

def _gzip_encode(s: str) -> str:
    import gzip
    compressed = gzip.compress(s.encode())
    return base64.b64encode(compressed).decode()

def _gzip_decode(s: str) -> str:
    import gzip
    try:
        padded = s + "=" * (4 - len(s) % 4) if len(s) % 4 else s
        compressed = base64.b64decode(padded)
        return gzip.decompress(compressed).decode("utf-8", errors="replace")
    except Exception as exc:
        return f"[gzip error: {exc}]"


# ── Operations: (label, fn) ────────────────────────────────────────────────────

OPERATIONS: list[tuple[str, Callable[[str], str]]] = [
    ("URL Encode",       _url_encode),
    ("URL Decode",       _url_decode),
    ("Base64 Encode",    _base64_encode),
    ("Base64 Decode",    _base64_decode),
    ("Base64URL Encode", _base64url_encode),
    ("Base64URL Decode", _base64url_decode),
    ("HTML Encode",      _html_encode),
    ("HTML Decode",      _html_decode),
    ("Hex Encode",       _hex_encode),
    ("Hex Decode",       _hex_decode),
    ("Unicode Encode",   _unicode_encode),
    ("Unicode Decode",   _unicode_decode),
    ("JWT Decode",       _jwt_decode),
    ("Gzip+B64 Encode",  _gzip_encode),
    ("Gzip+B64 Decode",  _gzip_decode),
    ("MD5",              _md5),
    ("SHA1",             _sha1),
    ("SHA256",           _sha256),
    ("SHA512",           _sha512),
]

_OP_MAP: dict[str, Callable[[str], str]] = {label: fn for label, fn in OPERATIONS}
OP_LABELS: list[str] = [label for label, _ in OPERATIONS]


def encode_op(operation: str, text: str) -> str:
    """Apply an operation by name. Raises KeyError if the operation is unknown."""
    fn = _OP_MAP.get(operation)
    if fn is None:
        raise KeyError(f"Unknown operation: {operation!r}")
    return fn(text)


def decode_op(operation: str, text: str) -> str:
    """Alias for encode_op (operations already include direction in name)."""
    return encode_op(operation, text)


def run_chain(operations: list[str], text: str) -> tuple[str, list[str]]:
    """Apply a chain of operations sequentially.

    Returns:
        (result, steps) — final text and list of intermediate values.
    """
    steps: list[str] = [text]
    current = text
    for op in operations:
        try:
            current = encode_op(op, current)
        except Exception as exc:
            current = f"[error in {op!r}: {exc}]"
        steps.append(current)
    return current, steps


def _detect_encoding(text: str) -> str | None:
    """Detect the most likely encoding of text. Returns operation label or None."""
    # JWT
    if re.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$", text):
        return "JWT Decode"
    # URL-encoded
    if "%" in text and re.search(r"%[0-9a-fA-F]{2}", text):
        return "URL Decode"
    # HTML entities
    if re.search(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);", text):
        return "HTML Decode"
    # Gzip+B64 (gzip magic bytes when decoded: 1f8b)
    b64_clean = text.strip().rstrip("=")
    if re.match(r"^[A-Za-z0-9+/]+$", b64_clean) and len(b64_clean) % 4 in (0, 2, 3):
        try:
            raw = base64.b64decode(text + "=" * (-len(text) % 4))
            if raw[:2] == b"\x1f\x8b":
                return "Gzip+B64 Decode"
        except Exception:
            pass
    # Hex
    if re.match(r"^[0-9a-fA-F]+$", text) and len(text) % 2 == 0 and len(text) >= 4:
        try:
            decoded = bytes.fromhex(text).decode("utf-8", errors="strict")
            if decoded.isprintable():
                return "Hex Decode"
        except Exception:
            pass
    # Base64URL (no +/ chars)
    if re.match(r"^[A-Za-z0-9_-]+=*$", text) and len(text) >= 8:
        try:
            decoded = _base64url_decode(text)
            if len(decoded) > 0 and sum(c.isprintable() for c in decoded) / len(decoded) > 0.8:
                return "Base64URL Decode"
        except Exception:
            pass
    # Base64 standard
    if re.match(r"^[A-Za-z0-9+/]+=*$", text) and len(text) >= 8 and len(text) % 4 in (0, 2, 3):
        try:
            decoded = _base64_decode(text)
            if len(decoded) > 0 and sum(c.isprintable() for c in decoded) / len(decoded) > 0.8:
                return "Base64 Decode"
        except Exception:
            pass
    return None


def decode_smart(text: str, max_depth: int = 8) -> str:
    """Auto-detect encoding and apply chain decoding until no more layers found.

    Tries up to max_depth decode operations. Shows the chain in the result
    by prepending a header line when multiple steps were applied.
    Returns the final decoded value.
    """
    text = text.strip()
    current = text
    chain: list[str] = []

    for _ in range(max_depth):
        op = _detect_encoding(current)
        if op is None:
            break
        try:
            next_val = encode_op(op, current)
            if next_val == current:
                break
            chain.append(op)
            current = next_val
        except Exception:
            break

    if not chain:
        return text
    return current


@dataclass
class DecoderChain:
    """Chain of operations with history."""

    operations: list[str] = field(default_factory=list)

    def add(self, op: str) -> None:
        if op not in OP_LABELS:
            raise KeyError(f"Unknown operation: {op!r}")
        self.operations.append(op)

    def remove(self, index: int) -> None:
        del self.operations[index]

    def clear(self) -> None:
        self.operations.clear()

    def run(self, text: str) -> tuple[str, list[str]]:
        return run_chain(self.operations, text)
