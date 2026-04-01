"""Property-based tests for RuleSet round-trip serialization (Property 1).

# Feature: github-pr-review-agent, Property 1: Rule_Set round-trip serialization
# Validates: Requirements 3.1, 3.8, 3.9
"""

import tempfile
import os

import pytest
from hypothesis import given, settings

from src.models import RuleSet
from src.review_rules_engine import ReviewRulesEngine
from tests.conftest import valid_rule_sets


engine = ReviewRulesEngine()


def _assert_rule_sets_equal(original: RuleSet, restored: RuleSet) -> None:
    """Assert two RuleSet objects are semantically equivalent."""
    assert original.version == restored.version
    assert original.file_allowlist == restored.file_allowlist
    assert len(original.rules) == len(restored.rules)
    for orig, rest in zip(original.rules, restored.rules):
        assert orig.id == rest.id
        assert orig.category == rest.category
        assert orig.description == rest.description
        assert orig.severity == rest.severity
        assert orig.prompt_or_pattern == rest.prompt_or_pattern
        assert orig.enabled == rest.enabled


@given(rule_set=valid_rule_sets())
@settings(max_examples=100)
def test_round_trip_yaml(rule_set: RuleSet) -> None:
    """For any valid RuleSet, print to YAML then parse back produces an equivalent RuleSet."""
    yaml_str = engine.print_rule_set(rule_set, format="yaml")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(yaml_str)
        tmp_path = f.name

    try:
        restored = engine.load(tmp_path)
        _assert_rule_sets_equal(rule_set, restored)
    finally:
        os.unlink(tmp_path)


@given(rule_set=valid_rule_sets())
@settings(max_examples=100)
def test_round_trip_json(rule_set: RuleSet) -> None:
    """For any valid RuleSet, print to JSON then parse back produces an equivalent RuleSet."""
    json_str = engine.print_rule_set(rule_set, format="json")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        f.write(json_str)
        tmp_path = f.name

    try:
        restored = engine.load(tmp_path)
        _assert_rule_sets_equal(rule_set, restored)
    finally:
        os.unlink(tmp_path)
