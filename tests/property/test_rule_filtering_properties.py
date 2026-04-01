"""Property-based tests for rule filtering by enabled flag and category (Property 3).

# Feature: github-pr-review-agent, Property 3: Rule filtering by enabled flag and category
# Validates: Requirements 3.6, 3.7
"""

from hypothesis import given, settings

from src.models import RuleSet
from src.review_rules_engine import ReviewRulesEngine
from tests.conftest import categories, valid_rule_sets

engine = ReviewRulesEngine()


@given(rule_set=valid_rule_sets(), category=categories)
@settings(max_examples=100)
def test_filter_by_category_returns_only_matching(
    rule_set: RuleSet, category: str
) -> None:
    """Filtering by category returns only rules whose category matches."""
    result = engine.filter_by_category(rule_set, category)
    assert all(r.category == category for r in result)
    expected = [r for r in rule_set.rules if r.category == category]
    assert result == expected


@given(rule_set=valid_rule_sets())
@settings(max_examples=100)
def test_get_enabled_rules_returns_only_enabled(rule_set: RuleSet) -> None:
    """Filtering by enabled returns only rules with enabled=True."""
    result = engine.get_enabled_rules(rule_set)
    assert all(r.enabled for r in result)
    expected = [r for r in rule_set.rules if r.enabled]
    assert result == expected


@given(rule_set=valid_rule_sets())
@settings(max_examples=100)
def test_category_filter_union_equals_full_list(rule_set: RuleSet) -> None:
    """The union of filtering by all distinct categories equals the full rule list."""
    present_categories = {r.category for r in rule_set.rules}
    union: list = []
    for cat in sorted(present_categories):
        union.extend(engine.filter_by_category(rule_set, cat))
    assert len(union) == len(rule_set.rules)
    assert set(id(r) for r in union) == set(id(r) for r in rule_set.rules)


@given(rule_set=valid_rule_sets(), category=categories)
@settings(max_examples=100)
def test_category_filter_is_subset(rule_set: RuleSet, category: str) -> None:
    """Filtered results are always a subset of the original rules."""
    result = engine.filter_by_category(rule_set, category)
    for r in result:
        assert r in rule_set.rules


@given(rule_set=valid_rule_sets())
@settings(max_examples=100)
def test_enabled_filter_is_subset(rule_set: RuleSet) -> None:
    """Enabled-filtered results are always a subset of the original rules."""
    result = engine.get_enabled_rules(rule_set)
    for r in result:
        assert r in rule_set.rules
