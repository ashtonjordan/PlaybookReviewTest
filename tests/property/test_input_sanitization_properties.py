"""Property-based tests for input sanitization (Property 19).

# Feature: github-pr-review-agent, Property 19: Input sanitization rejects malicious payloads
# Validates: Requirements 8.4
"""

import string

from hypothesis import given, settings
import hypothesis.strategies as st

from src.prompt_guard import PromptGuard

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strings that contain null bytes — built by inserting \x00 into normal text
strings_with_nulls = st.builds(
    lambda prefix, suffix: prefix + "\x00" + suffix,
    prefix=st.text(min_size=0, max_size=100),
    suffix=st.text(min_size=0, max_size=100),
)

# Control characters that should be stripped (0x01-0x08, 0x0B, 0x0C, 0x0E-0x1F, 0x7F)
_BAD_CONTROLS = "".join(
    chr(c)
    for c in list(range(0x01, 0x09)) + [0x0B, 0x0C] + list(range(0x0E, 0x20)) + [0x7F]
)

strings_with_control_chars = st.text(
    alphabet=st.characters(
        whitelist_characters=_BAD_CONTROLS + "abc123",
    ),
    min_size=1,
    max_size=200,
).filter(lambda s: any(c in _BAD_CONTROLS for c in s))

# Clean strings: printable ASCII + whitespace (\n, \r, \t) — no control chars
clean_strings = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        whitelist_characters="\n\r\t ",
    ),
    min_size=0,
    max_size=200,
).filter(lambda s: not any(c in _BAD_CONTROLS or c == "\x00" for c in s))

# Arbitrary text for general sanitization tests
arbitrary_text = st.text(min_size=0, max_size=500)

# Max-length values for truncation tests
max_lengths = st.integers(min_value=1, max_value=500)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

# **Validates: Requirements 8.4**


@given(value=arbitrary_text)
@settings(max_examples=100)
def test_sanitized_output_never_contains_null_bytes(value: str) -> None:
    """Sanitized output never contains null bytes."""
    result = PromptGuard.sanitize_input(value)
    assert "\x00" not in result


@given(value=arbitrary_text)
@settings(max_examples=100)
def test_sanitized_output_never_contains_bad_control_chars(value: str) -> None:
    """Sanitized output never contains control characters except \\n, \\r, \\t."""
    result = PromptGuard.sanitize_input(value)
    for ch in result:
        code = ord(ch)
        if code < 0x20 or code == 0x7F:
            assert ch in ("\n", "\r", "\t"), (
                f"Control char U+{code:04X} found in sanitized output"
            )


@given(value=arbitrary_text, max_length=max_lengths)
@settings(max_examples=100)
def test_sanitized_output_length_never_exceeds_max_length(
    value: str, max_length: int
) -> None:
    """Sanitized output length never exceeds max_length."""
    result = PromptGuard.sanitize_input(value, max_length=max_length)
    assert len(result) <= max_length


@given(value=strings_with_nulls)
@settings(max_examples=100)
def test_validate_input_returns_false_for_strings_with_null_bytes(
    value: str,
) -> None:
    """validate_input returns False for strings containing null bytes."""
    assert PromptGuard.validate_input(value) is False


@given(max_length=st.integers(min_value=1, max_value=100))
@settings(max_examples=100)
def test_validate_input_returns_false_for_strings_exceeding_max_length(
    max_length: int,
) -> None:
    """validate_input returns False for strings exceeding max_length."""
    value = "a" * (max_length + 1)
    assert PromptGuard.validate_input(value, max_length=max_length) is False


@given(value=clean_strings)
@settings(max_examples=100)
def test_validate_input_returns_true_for_clean_strings(value: str) -> None:
    """validate_input returns True for clean strings (no null bytes, within length)."""
    assert PromptGuard.validate_input(value, max_length=10000) is True


@given(value=clean_strings)
@settings(max_examples=100)
def test_sanitization_preserves_normal_text_content(value: str) -> None:
    """Sanitization preserves normal text content (alphanumeric, spaces, punctuation)."""
    result = PromptGuard.sanitize_input(value)
    assert result == value, "Clean text was altered by sanitization"
