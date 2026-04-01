"""Property-based tests for ReviewReportGenerator (Properties 4 and 5).

# Feature: github-pr-review-agent, Property 4: Review verdict is "fail" if and only if any finding has severity "error"
# Feature: github-pr-review-agent, Property 5: Review report summary counts match actual findings
# Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5
"""

from collections import Counter

from hypothesis import given, settings
import hypothesis.strategies as st

from src.models import Finding, Severity
from src.report_generator import ReviewReportGenerator
from tests.conftest import valid_findings

generator = ReviewReportGenerator()

correlation_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())


# --- Property 4: Verdict is "fail" iff any finding has severity "error" ---


@given(
    findings=st.lists(valid_findings(), min_size=0, max_size=20),
    cid=correlation_ids,
)
@settings(max_examples=100)
def test_verdict_fail_iff_error_present(findings: list[Finding], cid: str) -> None:
    """**Validates: Requirements 5.1, 5.2, 5.3**

    For any list of Findings, verdict is "fail" when at least one Finding has
    severity ERROR, and "pass" when no Finding has severity ERROR.
    """
    report = generator.generate(findings, cid)
    has_error = any(f.severity == Severity.ERROR for f in findings)

    if has_error:
        assert report.verdict == "fail"
    else:
        assert report.verdict == "pass"


@given(cid=correlation_ids)
@settings(max_examples=100)
def test_empty_findings_verdict_is_pass(cid: str) -> None:
    """**Validates: Requirements 5.1, 5.2, 5.3**

    Empty findings list always produces a "pass" verdict.
    """
    report = generator.generate([], cid)
    assert report.verdict == "pass"


# --- Property 5: Summary counts match actual findings ---


@given(
    findings=st.lists(valid_findings(), min_size=0, max_size=20),
    cid=correlation_ids,
)
@settings(max_examples=100)
def test_summary_counts_match_actual(findings: list[Finding], cid: str) -> None:
    """**Validates: Requirements 5.4, 5.5**

    Summary severity counts equal the actual count of findings at each severity level.
    """
    report = generator.generate(findings, cid)
    actual_counts = Counter(f.severity for f in findings)

    for sev in Severity:
        assert report.summary[sev.value] == actual_counts.get(sev, 0)


@given(
    findings=st.lists(valid_findings(), min_size=0, max_size=20),
    cid=correlation_ids,
)
@settings(max_examples=100)
def test_all_findings_have_required_fields(findings: list[Finding], cid: str) -> None:
    """**Validates: Requirements 5.4, 5.5**

    Every finding in the report contains all required fields.
    """
    report = generator.generate(findings, cid)

    for f in report.findings:
        assert f.file_path is not None
        assert f.line_start is not None
        assert f.line_end is not None
        assert f.rule_id is not None
        assert f.category is not None
        assert f.severity is not None
        assert f.description is not None


# --- Property 6: Verdict-to-check-status mapping ---
# Feature: github-pr-review-agent, Property 6: Verdict-to-check-status mapping
# Validates: Requirements 6.1, 6.2

from src.report_generator import ReviewReportGenerator as _RRG
from src.github_api_client import GitHubAPIClient

_gen = _RRG()


@given(
    findings=st.lists(valid_findings(), min_size=0, max_size=20),
    cid=correlation_ids,
)
@settings(max_examples=100)
def test_verdict_pass_maps_to_success(findings: list[Finding], cid: str) -> None:
    """**Validates: Requirements 6.1, 6.2**

    For any ReviewReport with verdict "pass", the check conclusion is "success".
    For any ReviewReport with verdict "fail", the check conclusion is "failure".
    """
    report = _gen.generate(findings, cid)
    conclusion = GitHubAPIClient.verdict_to_conclusion(report.verdict)

    if report.verdict == "pass":
        assert conclusion == "success"
    else:
        assert report.verdict == "fail"
        assert conclusion == "failure"


# --- Property 7: Findings produce inline review comments at correct locations ---
# Feature: github-pr-review-agent, Property 7: Findings produce inline review comments at correct locations
# Validates: Requirements 6.3

from src.models import ReviewReport as _RR


@given(
    findings=st.lists(valid_findings(), min_size=1, max_size=20),
    cid=correlation_ids,
)
@settings(max_examples=100)
def test_findings_produce_correct_review_comments(
    findings: list[Finding], cid: str
) -> None:
    """**Validates: Requirements 6.3**

    Each finding maps to a ReviewComment with matching file_path, line, and description.
    """
    report = _gen.generate(findings, cid)
    comments = GitHubAPIClient.findings_to_comments(report)

    assert len(comments) == len(report.findings)

    for finding, comment in zip(report.findings, comments):
        assert comment.file_path == finding.file_path
        assert comment.line == finding.line_start
        assert comment.body == finding.description
