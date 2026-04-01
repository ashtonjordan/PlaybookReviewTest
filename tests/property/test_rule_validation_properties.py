"""Property-based tests for rule validation (Property 2).

# Feature: github-pr-review-agent, Property 2: Rule validation rejects incomplete or invalid rules
# Validates: Requirements 3.2, 3.3, 3.4
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from src.models import VALID_CATEGORIES, Rule, Severity
from src.review_rules_engine import ReviewRulesEngine
from tests.conftest import categories, rule_ids, safe_text, severities

engine = ReviewRulesEngine()

# --- Strategies for invalid rules ---

# Strings that are empty or whitespace-only (invalid for required text fields)
blank_text = st.sampled_from(["", " ", "  ", "\t", "\n"])

# Category values that are NOT in VALID_CATEGORIES
invalid_categories = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip() and s not in VALID_CATEGORIES)


@given(
    valid_id=rule_ids,
    valid_category=categories,
    valid_description=safe_text,
    valid_severity=severities,
    valid_pattern=safe_text,
    field_to_blank=st.sampled_from(
        ["id", "category", "description", "prompt_or_pattern"]
    ),
    blank=blank_text,
)
@settings(max_examples=100)
def test_blank_required_field_rejected(
    valid_id: str,
    valid_category: str,
    valid_description: str,
    valid_severity: Severity,
    valid_pattern: str,
    field_to_blank: str,
    blank: str,
) -> None:
    """For any Rule with a required string field set to blank/whitespace, validation rejects it."""
    kwargs = {
        "id": valid_id,
        "category": valid_category,
        "description": valid_description,
        "severity": valid_severity,
        "prompt_or_pattern": valid_pattern,
    }
    kwargs[field_to_blank] = blank

    rule = Rule(**kwargs)
    errors = engine.validate_rule(rule)

    assert len(errors) > 0, f"Expected validation errors for blank '{field_to_blank}'"
    matching = [
        e
        for e in errors
        if field_to_blank in e.lower() or field_to_blank.replace("_", " ") in e.lower()
    ]
    assert len(matching) > 0, (
        f"Expected error mentioning '{field_to_blank}', got: {errors}"
    )


@given(
    valid_id=rule_ids,
    bad_category=invalid_categories,
    valid_description=safe_text,
    valid_severity=severities,
    valid_pattern=safe_text,
)
@settings(max_examples=100)
def test_invalid_category_rejected(
    valid_id: str,
    bad_category: str,
    valid_description: str,
    valid_severity: Severity,
    valid_pattern: str,
) -> None:
    """For any Rule with a category not in VALID_CATEGORIES, validation rejects it with a descriptive error."""
    rule = Rule(
        id=valid_id,
        category=bad_category,
        description=valid_description,
        severity=valid_severity,
        prompt_or_pattern=valid_pattern,
    )
    errors = engine.validate_rule(rule)

    assert len(errors) > 0, (
        f"Expected validation error for invalid category '{bad_category}'"
    )
    assert any("category" in e.lower() for e in errors), (
        f"Expected error mentioning 'category', got: {errors}"
    )
    assert any(bad_category in e for e in errors), (
        f"Expected error to include the invalid category value '{bad_category}', got: {errors}"
    )


@given(
    valid_id=rule_ids,
    valid_category=categories,
    valid_description=safe_text,
    valid_severity=severities,
    valid_pattern=safe_text,
    enabled=st.booleans(),
)
@settings(max_examples=100)
def test_valid_rule_accepted(
    valid_id: str,
    valid_category: str,
    valid_description: str,
    valid_severity: Severity,
    valid_pattern: str,
    enabled: bool,
) -> None:
    """For any Rule with all valid fields, validation returns no errors (sanity check)."""
    rule = Rule(
        id=valid_id,
        category=valid_category,
        description=valid_description,
        severity=valid_severity,
        prompt_or_pattern=valid_pattern,
        enabled=enabled,
    )
    errors = engine.validate_rule(rule)
    assert errors == [], f"Expected no errors for valid rule, got: {errors}"
