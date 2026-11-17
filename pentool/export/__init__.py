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

from pentool.export._base import SEVERITY_COLOR, SEVERITY_EMOJI, BaseExporter, FindingData, ReportData

# ── Concrete exporters (lazy — avoid circular imports) ────────────────────


def MarkdownExporter(*args, **kw):  # noqa: N802 — фабрика сохраняет публичное имя класса
    """Lazy-loaded MarkdownExporter."""
    from pentool.export.markdown import MarkdownExporter as _MarkdownExporter

    return _MarkdownExporter(*args, **kw)


def HtmlExporter(*args, **kw):  # noqa: N802 — фабрика сохраняет публичное имя класса
    """Lazy-loaded HtmlExporter."""
    from pentool.export.html import HtmlExporter as _HtmlExporter

    return _HtmlExporter(*args, **kw)


__all__ = [
    "BaseExporter",
    "FindingData",
    "ReportData",
    "SEVERITY_COLOR",
    "SEVERITY_EMOJI",
    "MarkdownExporter",
    "HtmlExporter",
]
