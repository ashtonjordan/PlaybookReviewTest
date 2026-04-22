"""Property-based tests for PromptGuard.validate_response_schema (Property 15).

# Feature: github-pr-review-agent, Property 15: Output JSON schema validation
# Validates: Requirements 9.5
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from src.prompt_guard import PromptGuard

guard = PromptGuard()

# --- Strategies ---

valid_severities = st.sampled_from(["error", "warning", "info"])

safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" -_"
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())

file_paths = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="/_-."
    ),
    min_size=3,
    max_size=60,
).filter(lambda s: s.strip())

line_numbers = st.integers(min_value=1, max_value=5000)

rule_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())


@st.composite
def valid_finding_dicts(draw: st.DrawFn) -> dict:
    """Generate a finding dict that conforms to the expected schema."""
    return {
        "file_path": draw(file_paths),
        "line_number": draw(line_numbers),
        "rule_id": draw(rule_ids),
        "severity": draw(valid_severities),
        "description": draw(safe_text),
    }


@st.composite
def valid_responses(draw: st.DrawFn) -> dict:
    """Generate a response dict with a valid findings array."""
    findings = draw(st.lists(valid_finding_dicts(), min_size=0, max_size=10))
    return {"findings": findings}


# Strategies for invalid responses

invalid_severities = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in {"error", "warning", "info"}
)

required_fields = ["file_path", "line_number", "rule_id", "severity", "description"]


@st.composite
def finding_missing_one_field(draw: st.DrawFn) -> dict:
    """Generate a finding dict with exactly one required field removed."""
    full = draw(valid_finding_dicts())
    field_to_remove = draw(st.sampled_from(required_fields))
    del full[field_to_remove]
    return full


@st.composite
def finding_with_invalid_severity(draw: st.DrawFn) -> dict:
    """Generate a finding dict with an invalid severity value."""
    finding = draw(valid_finding_dicts())
    finding["severity"] = draw(invalid_severities)
    return finding


# --- Property 15: Output JSON schema validation ---
# **Validates: Requirements 9.5**


@given(response=valid_responses())
@settings(max_examples=100)
def test_valid_responses_are_accepted(response: dict) -> None:
    """Any response with a findings array where each finding has all required fields
    and a valid severity should be accepted by the schema validator."""
    assert guard.validate_response_schema(response) is True


@given(findings=st.lists(valid_finding_dicts(), min_size=0, max_size=10))
@settings(max_examples=100)
def test_valid_response_with_extra_fields_accepted(findings: list[dict]) -> None:
    """Responses with extra fields beyond the required ones should still be accepted."""
    for f in findings:
        f["remediation"] = "Fix this issue"
        f["extra_field"] = 42
    response = {"findings": findings}
    assert guard.validate_response_schema(response) is True


@given(bad_finding=finding_missing_one_field())
@settings(max_examples=100)
def test_finding_missing_required_field_is_rejected(bad_finding: dict) -> None:
    """A response containing a finding with any single required field missing
    should be rejected."""
    response = {"findings": [bad_finding]}
    assert guard.validate_response_schema(response) is False


@given(bad_finding=finding_with_invalid_severity())
@settings(max_examples=100)
def test_finding_with_invalid_severity_is_rejected(bad_finding: dict) -> None:
    """A response containing a finding with a severity not in {error, warning, info}
    should be rejected."""
    response = {"findings": [bad_finding]}
    assert guard.validate_response_schema(response) is False


@given(
    valid_findings=st.lists(valid_finding_dicts(), min_size=1, max_size=5),
    bad_finding=finding_missing_one_field(),
)
@settings(max_examples=100)
def test_mix_of_valid_and_invalid_findings_is_rejected(
    valid_findings: list[dict], bad_finding: dict
) -> None:
    """A response where at least one finding is invalid should be rejected,
    even if other findings are valid."""
    response = {"findings": valid_findings + [bad_finding]}
    assert guard.validate_response_schema(response) is False


@given(non_dict=st.one_of(st.text(), st.integers(), st.lists(st.integers()), st.none()))
@settings(max_examples=100)
def test_non_dict_response_is_rejected(non_dict) -> None:
    """Any response that is not a dict should be rejected."""
    assert guard.validate_response_schema(non_dict) is False


@given(
    bad_findings_value=st.one_of(
        st.text(), st.integers(), st.none(), st.dictionaries(st.text(), st.text())
    )
)
@settings(max_examples=100)
def test_findings_not_a_list_is_rejected(bad_findings_value) -> None:
    """A response where 'findings' is not a list should be rejected."""
    response = {"findings": bad_findings_value}
    assert guard.validate_response_schema(response) is False


@given(data=st.data())
@settings(max_examples=100)
def test_response_without_findings_key_is_rejected(data: st.DataObject) -> None:
    """A dict without a 'findings' key should be rejected."""
    other_key = data.draw(
        st.text(min_size=1, max_size=20).filter(lambda s: s != "findings")
    )
    response = {other_key: []}
    assert guard.validate_response_schema(response) is False


@given(
    non_dict_item=st.one_of(
        st.text(), st.integers(), st.lists(st.integers()), st.none()
    )
)
@settings(max_examples=100)
def test_findings_containing_non_dict_items_is_rejected(non_dict_item) -> None:
    """A response where the findings array contains non-dict items should be rejected."""
    response = {"findings": [non_dict_item]}
    assert guard.validate_response_schema(response) is False


def test_empty_findings_list_is_accepted() -> None:
    """A response with an empty findings array is valid (no issues found)."""
    assert guard.validate_response_schema({"findings": []}) is True
