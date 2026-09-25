"""Export subsystem for Pentool — generates reports in multiple formats.

Architecture::

    FindingData       — one vulnerability (normalised from scanner_api.Finding)
    ReportData        — full report: target, summary, findings list
    BaseExporter      — abstract: take ReportData → produce output (str / bytes)

    MarkdownExporter  — FREE: minimal .md
    HtmlExporter      — FREE: minimal .html
    ProHtmlExporter   — PRO: full HTML with executive summary
    HackerOneExporter — PRO: HackerOne-compatible JSON
    BugcrowdExporter  — PRO: Bugcrowd-compatible CSV
    DefectDojoExporter— PRO: DefectDojo-compatible JSON

Usage (FREE)::

    from pentool.export import ReportData, MarkdownExporter, HtmlExporter

    report = ReportData(
        target="example.com",
        findings=[...],
        summary={"critical": 1, "high": 3, ...},
    )
    md = MarkdownExporter().export(report)     # str
    html = HtmlExporter().export(report)        # str

Usage (PRO)::

    from pentool.export.hackerone import HackerOneExporter
    h1_json = HackerOneExporter().export(report)  # str (JSON body for H1 API)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Data structures ─────────────────────────────────────────────────────


@dataclass
class FindingData:
    """Normalised finding — one discovered vulnerability.

    This is an exporter-agnostic representation.  Convert from the PRO
    scanner_api.Finding or from any other source via ``from_finding``.
    """

    title: str
    severity: str  # critical | high | medium | low | info
    url: str
    cwe: int | None = None
    cvss: float | None = None
    parameter: str = ""
    payload: str = ""
    evidence: str = ""
    description: str = ""
    remediation: str = ""
    confidence: str = "firm"  # firm | tentative | weak
    request_raw: str = ""
    response_raw: str = ""
    type: str = ""  # sqli, xss, lfi, …
    timestamp: str = ""

    @classmethod
    def from_finding(cls, finding: Any) -> "FindingData":
        """Build from PRO scanner_api.Finding (or any object with same attrs)."""
        ts = getattr(finding, "timestamp", None)
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        elif ts is None:
            ts = datetime.now(timezone.utc).isoformat()
        cwe_str = getattr(finding, "cwe", "") or ""
        try:
            cwe = int(cwe_str.replace("CWE-", ""))
        except (ValueError, TypeError):
            cwe = None
        return cls(
            title=getattr(finding, "name", getattr(finding, "title", "")),
            severity=getattr(finding, "severity", "info"),
            url=getattr(finding, "url", ""),
            cwe=cwe,
            cvss=getattr(finding, "cvss_score", None) or None,
            parameter=getattr(finding, "parameter", ""),
            payload=getattr(finding, "payload", ""),
            evidence=getattr(finding, "evidence", ""),
            description=getattr(finding, "description", ""),
            remediation=getattr(finding, "remediation", ""),
            confidence=_confidence(getattr(finding, "ai_confidence", 1.0)),
            request_raw=getattr(finding, "request_raw", ""),
            response_raw=getattr(finding, "response_raw", ""),
            type=getattr(finding, "type", ""),
            timestamp=ts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "severity": self.severity,
            "url": self.url,
            "cwe": self.cwe,
            "cvss": self.cvss,
            "parameter": self.parameter,
            "payload": self.payload,
            "evidence": self.evidence,
            "description": self.description,
            "remediation": self.remediation,
            "confidence": self.confidence,
            "request_raw": self.request_raw,
            "response_raw": self.response_raw,
            "type": self.type,
            "timestamp": self.timestamp,
        }


def _confidence(ai_conf: float) -> str:
    if ai_conf >= 0.9:
        return "firm"
    if ai_conf >= 0.5:
        return "tentative"
    return "weak"


@dataclass
class ReportData:
    """Full report payload passed to every exporter."""

    target: str
    findings: list[FindingData] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=lambda: {
        "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
    })
    tool_version: str = ""
    start_time: str = ""
    end_time: str = ""
    scope: list[str] = field(default_factory=list)
    scan_checks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.summary or all(v == 0 for v in self.summary.values()):
            self._recalc_summary()

    def _recalc_summary(self) -> None:
        s: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in self.findings:
            sev = f.severity.lower()
            if sev in s:
                s[sev] += 1
        self.summary = s


# ── Base exporter ────────────────────────────────────────────────────────


class BaseExporter(ABC):
    """Every exporter implements ``export(report) → str``."""

    @abstractmethod
    def export(self, report: ReportData) -> str:
        ...

    def extension(self) -> str:
        """File extension without dot, e.g. ``"md"``, ``"html"``."""
        return "txt"


# ── Severity helpers ─────────────────────────────────────────────────────

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🔵",
    "info":     "⚪",
}

SEVERITY_COLOR = {
    "critical": "#dc3545",
    "high":     "#fd7e14",
    "medium":   "#ffc107",
    "low":      "#0d6efd",
    "info":     "#6c757d",
}