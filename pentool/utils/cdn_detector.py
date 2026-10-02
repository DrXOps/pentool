"""CDN detector — identifies CDN providers by CNAME + response headers.

Pure Python, zero deps. Uses a built-in database of known CDN signatures.

Usage::

    from pentool.utils.cdn_detector import detect_cdn, CdnMatch

    match = detect_cdn(host="admin.example.com", cname="admin.example.com.cdn.cloudflare.net")
    # → CdnMatch(provider="Cloudflare", confidence=1.0)

    match = detect_cdn(headers={"server": "cloudflare", "cf-ray": "..."})
    # → CdnMatch(provider="Cloudflare", confidence=0.95, evidence="header:server=cloudflare")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── data ──────────────────────────────────────────────────────────────


@dataclass
class CdnMatch:
    """Result of CDN detection for a single host."""

    provider: str           # "Cloudflare", "Akamai", etc.
    confidence: float       # 0.0 – 1.0
    evidence: str           # human-readable explanation
    detected_by: str        # "cname" | "header" | "ip_range"


# ── CDN signatures ───────────────────────────────────────────────────

CdnSignature = dict[str, Any]

# Each signature has:
#   provider - display name
#   cname_suffixes - list of CNAME suffixes to match
#   header_signatures - dict of header_name → substr to match
#   ip_ranges - list of CIDR ranges (optional, unused for now)

CDN_DB: list[CdnSignature] = [
    {
        "provider": "Cloudflare",
        "cname_suffixes": [
            ".cloudflare.net",
            ".cf-",
            ".cdn.cloudflare.net",
        ],
        "header_signatures": {
            "server": "cloudflare",
            "cf-ray": "",
        },
    },
    {
        "provider": "Akamai",
        "cname_suffixes": [
            ".akamai.net",
            ".akamaiedge.net",
            ".akam.net",
        ],
        "header_signatures": {
            "server": "Akamai",
            "x-akamai-": "",
            "x-akamai-request-id": "",
            "x-akamai-edge": "",
        },
    },
    {
        "provider": "Fastly",
        "cname_suffixes": [
            ".fastly.net",
            ".fastlylb.net",
            ".global.fastly.net",
        ],
        "header_signatures": {
            "x-fastly-": "",
            "x-fastly-request-id": "",
        },
    },
    {
        "provider": "Amazon CloudFront",
        "cname_suffixes": [
            ".cloudfront.net",
        ],
        "header_signatures": {
            "x-amz-cf-id": "",
            "x-amz-cf-": "",
            "via": "cloudfront",
            "server": "AmazonS3",
        },
    },
    {
        "provider": "BunnyCDN",
        "cname_suffixes": [
            ".bunnycdn.net",
            ".b-cdn.net",
        ],
        "header_signatures": {
            "server": "bunnycdn",
        },
    },
    {
        "provider": "KeyCDN",
        "cname_suffixes": [
            ".keycdn.com",
            ".keycdn.net",
        ],
        "header_signatures": {
            "server": "keycdn",
        },
    },
    {
        "provider": "StackPath",
        "cname_suffixes": [
            ".stackpathcdn.com",
            ".highwinds.com",
        ],
        "header_signatures": {
            "server": "stackpath",
        },
    },
    {
        "provider": "Google Cloud CDN",
        "cname_suffixes": [
            ".gcloud.net",
            ".googleusercontent.com",
        ],
        "header_signatures": {},
    },
    {
        "provider": "Azure CDN (Microsoft)",
        "cname_suffixes": [
            ".azureedge.net",
            ".azurecdn.net",
            ".msecnd.net",
            ".vo.msecnd.net",
        ],
        "header_signatures": {
            "x-azure-": "",
            "x-azure-fd": "",
        },
    },
    {
        "provider": "Imperva (Incapsula)",
        "cname_suffixes": [
            ".incapsula.com",
            ".impervadns.net",
        ],
        "header_signatures": {
            "x-iinfo": "",
            "x-cdn": "incapsula",
            "server": "Incapsula",
        },
    },
    {
        "provider": "Sucuri",
        "cname_suffixes": [
            ".sucuri.net",
        ],
        "header_signatures": {
            "x-sucuri-": "",
            "x-sucuri-cache": "",
        },
    },
    {
        "provider": "Section.io",
        "cname_suffixes": [
            ".section.io",
            ".sectioncdn",
        ],
        "header_signatures": {
            "x-section-": "",
            "x-section-cache": "",
        },
    },
    {
        "provider": "CDNetworks",
        "cname_suffixes": [
            ".cdnetworks.net",
            ".cdngc.net",
        ],
        "header_signatures": {},
    },
    {
        "provider": "ChinaCDN",
        "cname_suffixes": [
            ".chinacdn.net",
            ".ccdn.net",
        ],
        "header_signatures": {},
    },
    {
        "provider": "OVH CDN",
        "cname_suffixes": [
            ".ovh.net",
        ],
        "header_signatures": {},
    },
]


# ── public API ────────────────────────────────────────────────────────


def detect_cdn(
    host: str | None = None,
    headers: dict[str, str] | None = None,
    cname: str | None = None,
) -> CdnMatch | None:
    """Detect CDN provider for a host.

    Checks in order:
    1. CNAME match (highest confidence)
    2. Response headers match
    3. Host suffix match (lowest confidence)

    Returns the **best** match (highest confidence), or None if no CDN detected.

    Args:
        host: hostname (used for suffix matching only).
        headers: response headers dict (case-insensitive keys).
        cname: CNAME record value from DNS lookup.

    Returns:
        CdnMatch or None.
    """
    candidates: list[tuple[float, CdnMatch]] = []

    for sig in CDN_DB:
        # 1. CNAME match → confidence 1.0
        if cname:
            cname_lower = cname.lower().strip(".")
            for suffix in sig["cname_suffixes"]:
                if cname_lower.endswith(suffix.strip(".")):
                    candidates.append((
                        1.0,
                        CdnMatch(
                            provider=sig["provider"],
                            confidence=1.0,
                            evidence=f"CNAME: {cname}",
                            detected_by="cname",
                        ),
                    ))
                    break  # one match per signature

        # 2. Header match
        if headers:
            headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
            matched_headers: list[str] = []
            for hdr_name, hdr_value in sig["header_signatures"].items():
                hdr_lower = hdr_name.lower()
                for resp_hdr, resp_val in headers_lower.items():
                    if hdr_lower in resp_hdr:
                        if not hdr_value or hdr_value in resp_val:
                            matched_headers.append(f"{resp_hdr}={resp_val}")
                            break
            if matched_headers:
                confidence = _header_confidence(len(matched_headers))
                candidates.append((
                    confidence,
                    CdnMatch(
                        provider=sig["provider"],
                        confidence=confidence,
                        evidence=f"header:{'; '.join(matched_headers)}",
                        detected_by="header",
                    ),
                ))

        # 3. Host suffix match (weakest)
        if host:
            host_lower = host.lower().strip(".")
            for suffix in sig["cname_suffixes"]:
                # Remove leading dot for suffix check
                suffix_clean = suffix.strip(".")
                if host_lower.endswith(suffix_clean) or f".{suffix_clean}" in f".{host_lower}":
                    candidates.append((
                        0.5,
                        CdnMatch(
                            provider=sig["provider"],
                            confidence=0.5,
                            evidence=f"host suffix: {host}",
                            detected_by="ip_range",
                        ),
                    ))
                    break

    if not candidates:
        return None

    # Return highest-confidence match
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _header_confidence(matched_count: int) -> float:
    """Map number of matched headers to confidence."""
    if matched_count >= 3:
        return 0.98
    if matched_count >= 2:
        return 0.95
    return 0.85


# ── convenience ────────────────────────────────────────────────────────

# Map of known CDN providers for quick display purposes
KNOWN_CDN_PROVIDERS: set[str] = {sig["provider"] for sig in CDN_DB}