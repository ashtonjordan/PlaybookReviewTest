"""ReviewReportGenerator — assembles findings into a structured ReviewReport."""

from collections import Counter

from src.models import Finding, ReviewReport, Severity


class ReviewReportGenerator:
    """Generates structured Review_Reports from findings."""

    def generate(self, findings: list[Finding], correlation_id: str) -> ReviewReport:
        """Create a ReviewReport with verdict, summary, and per-finding details.

        Verdict is "fail" if any finding has severity ERROR, "pass" otherwise.
        Summary counts findings grouped by severity level.
        """
        severity_counts = Counter(f.severity for f in findings)
        summary = {s.value: severity_counts.get(s, 0) for s in Severity}

        has_error = any(f.severity == Severity.ERROR for f in findings)
        verdict = "fail" if has_error else "pass"

        return ReviewReport(
            verdict=verdict,
            findings=list(findings),
            summary=summary,
            correlation_id=correlation_id,
        )
