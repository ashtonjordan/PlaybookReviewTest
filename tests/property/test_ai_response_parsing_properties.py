"""Property tests for AI response parsing — produces structured findings.

Feature: github-pr-review-agent, Property 11: AI response parsing produces structured findings
Validates: Requirements 4.3
"""

from unittest.mock import MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from src.codeguard_loader import CodeGuardLoader
from src.github_api_client import GitHubAPIClient
from src.models import VALID_CATEGORIES, Finding, Severity
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.review_agent import ReviewAgent
from src.structured_logger import StructuredLogger

# --- Strategies ---

severities_str = st.sampled_from(["error", "warning", "info"])
categories = st.sampled_from(sorted(VALID_CATEGORIES))

safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" -_"
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())

rule_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())

file_paths = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="/_-."
    ),
    min_size=3,
    max_size=60,
).filter(lambda s: s.strip())

line_numbers = st.integers(min_value=1, max_value=5000)


@st.composite
def ai_finding_dicts(draw: st.DrawFn) -> dict:
    """Generate a well-formed AI finding dict matching the expected schema."""
    return {
        "file_path": draw(file_paths),
        "line_number": draw(line_numbers),
        "rule_id": draw(rule_ids),
        "category": draw(categories),
        "severity": draw(severities_str),
        "description": draw(safe_text),
    }


@st.composite
def ai_response_dicts(draw: st.DrawFn) -> dict:
    """Generate a well-formed AI response dict with a findings array."""
    findings = draw(st.lists(ai_finding_dicts(), min_size=1, max_size=15))
    return {"findings": findings}


def _make_agent() -> ReviewAgent:
    """Create a ReviewAgent with mocked dependencies."""
    github_client = MagicMock(spec=GitHubAPIClient)
    codeguard_loader = MagicMock(spec=CodeGuardLoader)
    prompt_guard = MagicMock(spec=PromptGuard)
    report_generator = MagicMock(spec=ReviewReportGenerator)
    logger = MagicMock(spec=StructuredLogger)
    logger.correlation_id = "test-correlation-id"

    return ReviewAgent(
        github_client=github_client,
        codeguard_loader=codeguard_loader,
        prompt_guard=prompt_guard,
        report_generator=report_generator,
        logger=logger,
    )


# --- Property 11: AI response parsing produces structured findings ---


@given(response=ai_response_dicts())
@settings(max_examples=100)
def test_parsed_findings_have_all_required_fields(response):
    """Property 11: For any well-formed AI response JSON, parsing should produce
    Finding objects where each has a valid file_path, line_number, rule_id,
    category, severity, and description.

    **Validates: Requirements 4.3**
    """
    agent = _make_agent()
    findings = agent._parse_ai_findings(response)

    assert len(findings) == len(response["findings"])

    for finding, raw in zip(findings, response["findings"]):
        assert isinstance(finding, Finding)

        # All required fields are populated from the source dict
        assert finding.file_path == raw["file_path"]
        assert finding.line_start == raw["line_number"]
        assert finding.line_end == raw["line_number"]
        assert finding.rule_id == raw["rule_id"]
        assert finding.category == raw["category"]
        assert isinstance(finding.severity, Severity)
        assert finding.severity.value == raw["severity"]
        assert finding.description == raw["description"]


@given(response=ai_response_dicts())
@settings(max_examples=100)
def test_parsed_findings_severity_is_valid_enum(response):
    """Property 11 (supplementary): Every parsed finding's severity must be a
    valid Severity enum member.

    **Validates: Requirements 4.3**
    """
    agent = _make_agent()
    findings = agent._parse_ai_findings(response)

    for finding in findings:
        assert finding.severity in list(Severity)


@given(
    file_path=file_paths,
    line_number=line_numbers,
    rule_id=rule_ids,
    description=safe_text,
    bad_severity=st.text(min_size=1, max_size=20).filter(
        lambda s: s.strip() and s.lower() not in ("error", "warning", "info")
    ),
)
@settings(max_examples=100)
def test_invalid_severity_defaults_to_info(
    file_path, line_number, rule_id, description, bad_severity
):
    """Property 11 (supplementary): When the AI response contains an unrecognized
    severity value, parsing should default to INFO rather than failing.

    **Validates: Requirements 4.3**
    """
    agent = _make_agent()
    response = {
        "findings": [
            {
                "file_path": file_path,
                "line_number": line_number,
                "rule_id": rule_id,
                "severity": bad_severity,
                "description": description,
            }
        ]
    }

    findings = agent._parse_ai_findings(response)

    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO


@settings(max_examples=100)
@given(data=st.data())
def test_empty_findings_array_produces_empty_list(data):
    """Property 11 (supplementary): An AI response with an empty findings array
    should produce an empty list of Finding objects.

    **Validates: Requirements 4.3**
    """
    agent = _make_agent()
    response = {"findings": []}

    findings = agent._parse_ai_findings(response)

    assert findings == []
