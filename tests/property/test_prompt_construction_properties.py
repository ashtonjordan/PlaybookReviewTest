"""Property tests for AIModelClient.build_prompt — prompt includes all required components.

Feature: github-pr-review-agent, Property 10: Prompt construction includes all required components and only changed files
Validates: Requirements 4.1, 4.2
"""

from unittest.mock import MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from src.ai_model_client import AIModelClient
from src.models import (
    VALID_CATEGORIES,
    FileDiff,
    Rule,
    Severity,
    WebexAPIRegistryData,
    WebexEndpoint,
)

# --- Strategies ---

severities = st.sampled_from(list(Severity))
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

# Unique filenames for diffs — alphanumeric with a code extension
code_extensions = st.sampled_from([".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp"])

languages = st.sampled_from(
    ["python", "javascript", "typescript", "java", "go", "rust", "cpp", None]
)

http_methods = st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH"])


@st.composite
def file_diffs(draw: st.DrawFn) -> FileDiff:
    """Generate a FileDiff with a unique-ish filename."""
    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="_-"
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s.strip())
    )
    ext = draw(code_extensions)
    return FileDiff(
        filename=f"src/{name}{ext}",
        patch=draw(safe_text),
        language=draw(languages),
    )


@st.composite
def rules(draw: st.DrawFn) -> Rule:
    """Generate a valid Rule."""
    return Rule(
        id=draw(rule_ids),
        category=draw(categories),
        description=draw(safe_text),
        severity=draw(severities),
        prompt_or_pattern=draw(safe_text),
        enabled=True,
    )


@st.composite
def webex_endpoints(draw: st.DrawFn) -> WebexEndpoint:
    """Generate a WebexEndpoint."""
    path = "/" + draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="/-_"
            ),
            min_size=1,
            max_size=40,
        ).filter(lambda s: s.strip())
    )
    return WebexEndpoint(
        path=path,
        method=draw(http_methods),
        technology=draw(safe_text),
        description=draw(safe_text),
    )


# Extra filenames that should NOT appear in the prompt
extra_filenames = (
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        ),
        min_size=3,
        max_size=20,
    )
    .filter(lambda s: s.strip())
    .map(lambda s: f"extra/{s}.xyz")
)


def _make_client() -> AIModelClient:
    """Create an AIModelClient with a mocked boto3 session."""
    mock_session = MagicMock()
    return AIModelClient(boto3_session=mock_session)


# --- Property 10: Prompt construction includes all required components and only changed files ---


@given(
    diffs=st.lists(file_diffs(), min_size=1, max_size=10),
    rule_list=st.lists(rules(), min_size=1, max_size=10),
    endpoints=st.lists(webex_endpoints(), min_size=1, max_size=10),
    extra_names=st.lists(extra_filenames, min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_prompt_contains_all_diffs_rules_and_registry(
    diffs, rule_list, endpoints, extra_names
):
    """Property 10: The constructed prompt includes all diff patches, all rule ids
    and descriptions, all registry endpoints, and no filenames from outside the diffs.

    **Validates: Requirements 4.1, 4.2**
    """
    client = _make_client()
    registry = WebexAPIRegistryData(endpoints=endpoints)

    prompt = client.build_prompt(diffs=diffs, rules=rule_list, registry=registry)

    # (a) Every diff's patch content appears in the prompt
    for diff in diffs:
        assert diff.patch in prompt, (
            f"Diff patch for {diff.filename} missing from prompt"
        )

    # (b) Every rule's id and description appear in the prompt
    for rule in rule_list:
        assert rule.id in prompt, f"Rule id '{rule.id}' missing from prompt"
        assert rule.description in prompt, (
            f"Rule description '{rule.description}' missing from prompt"
        )

    # (c) Registry endpoint paths and methods appear in the prompt
    for ep in endpoints:
        assert ep.path in prompt, f"Endpoint path '{ep.path}' missing from prompt"
        assert ep.method in prompt, f"Endpoint method '{ep.method}' missing from prompt"

    # (d) Extra filenames NOT in the diffs should not appear in the prompt
    diff_filenames = {d.filename for d in diffs}
    for extra in extra_names:
        if extra not in diff_filenames:
            assert extra not in prompt, (
                f"Extra filename '{extra}' should not appear in prompt"
            )

    # (e) Rules are grouped by category — each category header appears
    seen_categories = {r.category for r in rule_list}
    for cat in seen_categories:
        assert cat in prompt, f"Category '{cat}' header missing from prompt"


@given(
    diffs=st.lists(file_diffs(), min_size=1, max_size=5),
    rule_list=st.lists(rules(), min_size=1, max_size=5),
)
@settings(max_examples=100)
def test_prompt_without_registry_omits_registry_section(diffs, rule_list):
    """Property 10 (supplementary): When no registry is provided, the prompt should
    not contain the Webex API Registry section header.

    **Validates: Requirements 4.1, 4.2**
    """
    client = _make_client()

    prompt = client.build_prompt(diffs=diffs, rules=rule_list, registry=None)

    # Diffs and rules still present
    for diff in diffs:
        assert diff.patch in prompt
    for rule in rule_list:
        assert rule.id in prompt

    # Registry section should be absent
    assert "## Webex API Registry" not in prompt
