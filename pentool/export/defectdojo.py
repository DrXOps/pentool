"""PRO: DefectDojo-compatible JSON exporter.

Produces a JSON payload ready for DefectDojo's import API
(generic / finding format).  Compatible with DD >= 2.0.
"""

from __future__ import annotations

import json

from pentool.export import BaseExporter, FindingData, ReportData


class DefectDojoExporter(BaseExporter):
    """PRO: export findings as DefectDojo Import JSON.

    Uses the generic "Findings" format that DD accepts.
    """

    def extension(self) -> str:
        return "json"

    def export(self, report: ReportData) -> str:
        payload = {
            "product_name": f"Pentool: {report.target}",
            "engagement_name": f"Pentool Scan — {report.end_time or report.start_time or 'N/A'}",
            "findings": [self._finding_to_dd(f) for f in report.findings],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _finding_to_dd(self, f: FindingData) -> dict:
        return {
            "title": f.title,
            "severity": f.severity.capitalize(),
            "cwe": f.cwe or None,
            "cvssv3_score": f.cvss,
            "description": self._dd_description(f),
            "mitigation": f.remediation,
            "references": f"https://cwe.mitre.org/data/definitions/{f.cwe}.html" if f.cwe else "",
            "unsaved_request_resp": [
                f.request_raw[:2000] if f.request_raw else "",
                f.response_raw[:2000] if f.response_raw else "",
            ],
            "vuln_id_from_tool": f.type or "",
            "impact": self._impact(f),
            "active": True,
            "verified": f.confidence == "firm",
        }

    def _dd_description(self, f: FindingData) -> str:
        parts = [f"## {f.title}", ""]
        if f.url:
            parts.append(f"**URL:** `{f.url}`")
        if f.parameter:
            parts.append(f"**Parameter:** `{f.parameter}`")
        if f.payload:
            parts.append(f"**Payload:** `{f.payload}`")
        if f.cwe:
            parts.append(f"**CWE:** {f.cwe}")
        parts.append("")
        if f.description:
            parts.append(f.description)
            parts.append("")
        if f.evidence:
            parts.append("**Evidence:**")
            parts.append("```")
            parts.append(f.evidence[:1000])
            parts.append("```")
            parts.append("")
        return "\n".join(parts)

    def _impact(self, f: FindingData) -> str:
        sev = f.severity.lower()
        if sev == "critical":
            return "Complete compromise of confidentiality, integrity, and availability"
        if sev == "high":
            return "Significant impact on data security or system availability"
        if sev == "medium":
            return "Moderate security impact under specific conditions"
        if sev == "low":
            return "Minor security concern, limited impact"
        return "Informational issue"