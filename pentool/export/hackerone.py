"""PRO: HackerOne-compatible JSON exporter.

Produces a JSON payload ready for the HackerOne Import API
(https://api.hackerone.com/docs).

The output can be uploaded via:

.. code-block:: bash

   curl -u api_token: -X POST https://api.hackerone.com/v1/reports \\
     -H "Content-Type: application/json" -d @report.json
"""

from __future__ import annotations

import json

from pentool.export import BaseExporter, FindingData, ReportData


class HackerOneExporter(BaseExporter):
    """PRO: export findings as HackerOne Import JSON.

    Each finding becomes a separate vulnerability in the H1 report.
    """

    def extension(self) -> str:
        return "json"

    def export(self, report: ReportData) -> str:
        payload = self._build_payload(report)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_payload(self, report: ReportData) -> dict:
        vulnerabilities = []
        for f in report.findings:
            vuln = self._finding_to_vulnerability(f)
            if vuln:
                vulnerabilities.append(vuln)

        return {
            "data": {
                "type": "report",
                "attributes": {
                    "team_handle": "",  # user must fill in
                    "title": f"Pentool Scan: {report.target}",
                    "vulnerability_information": self._build_summary_md(report),
                    "severity_rating": self._overall_severity(report),
                    "weakness_id": self._pick_cwe(report),
                    "custom_fields": {},
                },
            },
            "included": vulnerabilities,
        }

    def _finding_to_vulnerability(self, f: FindingData) -> dict | None:
        if not f.title:
            return None
        return {
            "type": "vulnerability",
            "attributes": {
                "title": f.title,
                "severity_rating": f.severity,
                "vulnerability_information": self._finding_md(f),
                "weakness_id": f.cwe or None,
                "cvss_vector": None,
            },
        }

    def _finding_md(self, f: FindingData) -> str:
        lines = [f"## {f.title}", ""]
        if f.url:
            lines.append(f"**URL:** `{f.url}`")
        if f.parameter:
            lines.append(f"**Parameter:** `{f.parameter}`")
        if f.payload:
            lines.append(f"**Payload:** `{f.payload}`")
        if f.cwe:
            lines.append(f"**CWE:** {f.cwe}")
        lines.append("")
        if f.description:
            lines.append(f"{f.description}")
            lines.append("")
        if f.evidence:
            lines.append("**Evidence:**")
            lines.append("```")
            lines.append(f.evidence[:500])
            lines.append("```")
            lines.append("")
        if f.remediation:
            lines.append(f"**Remediation:** {f.remediation}")
            lines.append("")
        return "\n".join(lines)

    def _build_summary_md(self, report: ReportData) -> str:
        total = sum(report.summary.values())
        lines = [
            f"# Pentool Scan: {report.target}",
            "",
            "## Summary",
            "",
            f"**Total findings:** {total}",
        ]
        for sev in ("critical", "high", "medium", "low", "info"):
            cnt = report.summary.get(sev, 0)
            if cnt:
                lines.append(f"- **{sev.capitalize()}:** {cnt}")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _overall_severity(self, report: ReportData) -> str:
        for sev in ("critical", "high", "medium", "low"):
            if report.summary.get(sev, 0) > 0:
                return sev
        return "info"

    def _pick_cwe(self, report: ReportData) -> int | None:
        for f in report.findings:
            if f.cwe:
                return f.cwe
        return None