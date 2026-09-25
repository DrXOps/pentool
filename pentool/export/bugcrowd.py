"""PRO: Bugcrowd-compatible CSV exporter.

Produces a CSV file matching Bugcrowd's submission format columns.
Can be uploaded directly via Bugcrowd's bulk import.
"""

from __future__ import annotations

import csv
import io

from pentool.export import BaseExporter, FindingData, ReportData


class BugcrowdExporter(BaseExporter):
    """PRO: export findings as Bugcrowd-compatible CSV.

    Columns:
      Title, Vulnerability Type, URL, Severity, Description,
      Remediation, Proof of Concept, Impact, Reference
    """

    def extension(self) -> str:
        return "csv"

    def export(self, report: ReportData) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "Title", "Vulnerability Type", "URL", "Severity",
            "Description", "Remediation", "Proof of Concept",
            "Impact", "Reference",
        ])
        for f in report.findings:
            writer.writerow([
                f.title,
                f.type or f.title,
                f.url,
                f.severity,
                f.description,
                f.remediation,
                f.evidence[:500] if f.evidence else "",
                self._impact(f),
                f"https://cwe.mitre.org/data/definitions/{f.cwe}.html" if f.cwe else "",
            ])
        return buf.getvalue()

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