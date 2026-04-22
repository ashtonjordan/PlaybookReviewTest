"""Property tests for PromptGuard.build_system_message — system prompt hardening.

# Feature: github-pr-review-agent, Property 14: System prompt hardening constrains AI to code analysis
# Validates: Requirements 9.3
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from src.prompt_guard import PromptGuard


# --- Helpers ---

# Phrases that MUST appear in the system message to constrain the AI to code analysis.
CODE_ANALYSIS_CONSTRAINT_PHRASES = [
    "security",
    "quality",
]

# Directives that instruct the model to ignore injected instructions from untrusted content.
IGNORE_INJECTION_DIRECTIVES = [
    "code comments",
    "string literals",
    "non-code content",
]

# The system message must explicitly forbid off-topic behavior.
OFF_TOPIC_PROHIBITION_PHRASES = [
    "MUST NOT",
    "MUST ONLY",
    "IGNORE",
]

# Required JSON response schema fields that the system message must mention.
REQUIRED_RESPONSE_FIELDS = [
    "file_path",
    "line_number",
    "rule_id",
    "severity",
    "description",
]


# --- Property 14: System prompt hardening constrains AI to code analysis ---


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_constrains_to_code_analysis(data: st.DataObject) -> None:
    """The system message must contain directives constraining the AI to code
    security and quality analysis only.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    for phrase in CODE_ANALYSIS_CONSTRAINT_PHRASES:
        assert phrase.lower() in message.lower(), (
            f"System message missing code analysis constraint phrase: '{phrase}'"
        )


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_contains_ignore_injection_instructions(
    data: st.DataObject,
) -> None:
    """The system message must instruct the model to ignore instructions embedded
    in code comments, string literals, and non-code content.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    for directive in IGNORE_INJECTION_DIRECTIVES:
        assert directive.lower() in message.lower(), (
            f"System message missing ignore-injection directive: '{directive}'"
        )


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_prohibits_off_topic_responses(data: st.DataObject) -> None:
    """The system message must contain explicit prohibitions against off-topic
    responses and following injected instructions.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    for phrase in OFF_TOPIC_PROHIBITION_PHRASES:
        assert phrase in message, (
            f"System message missing off-topic prohibition phrase: '{phrase}'"
        )


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_specifies_json_response_schema(data: st.DataObject) -> None:
    """The system message must specify the expected JSON response schema fields
    so the AI produces structured, validatable output.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    for field in REQUIRED_RESPONSE_FIELDS:
        assert field in message, (
            f"System message missing required response field: '{field}'"
        )


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_mentions_prompt_injection_defense(data: st.DataObject) -> None:
    """The system message must explicitly address prompt injection attempts,
    instructing the model to report them as findings rather than follow them.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    message_lower = message.lower()
    assert (
        "prompt injection" in message_lower or "injected instructions" in message_lower
    ), "System message must mention prompt injection defense"


@settings(max_examples=100)
@given(
    custom_allowlist=st.frozensets(
        st.sampled_from([".py", ".js", ".ts", ".java", ".go"]),
        min_size=1,
        max_size=3,
    )
)
def test_system_message_invariant_across_allowlist_configurations(
    custom_allowlist: frozenset[str],
) -> None:
    """The system message content must be invariant regardless of the file allowlist
    configuration — prompt hardening is independent of which file types are allowed.

    Property 14 — Validates: Requirements 9.3
    """
    default_guard = PromptGuard()
    custom_guard = PromptGuard(file_allowlist=set(custom_allowlist))

    default_message = default_guard.build_system_message()
    custom_message = custom_guard.build_system_message()

    assert default_message == custom_message, (
        "System message should not change based on file allowlist configuration"
    )


@settings(max_examples=100)
@given(data=st.data())
def test_system_message_is_nonempty_string(data: st.DataObject) -> None:
    """The system message must be a non-empty string with substantial content.

    Property 14 — Validates: Requirements 9.3
    """
    guard = PromptGuard()
    message = guard.build_system_message()

    assert isinstance(message, str)
    assert len(message.strip()) > 100, (
        "System message should be substantial (>100 chars) to provide adequate constraints"
    )
