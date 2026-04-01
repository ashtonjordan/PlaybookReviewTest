"""Property-based tests for StructuredLogger (Properties 17 and 18).

# Feature: github-pr-review-agent, Property 17: Secret redaction in log output
# Feature: github-pr-review-agent, Property 18: Structured JSON log output
# Validates: Requirements 7.4, 7.5, 8.6
"""

import json
import re

from hypothesis import given, settings
import hypothesis.strategies as st

from src.structured_logger import StructuredLogger

correlation_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())

log_levels = st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR"])

safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" -_"
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())


# --- Strategies for generating specific secret types ---

aws_keys = st.from_regex(r"AKIA[0-9A-Z]{16}", fullmatch=True)

github_tokens = st.sampled_from(["ghp_", "ghs_", "gho_", "ghu_"]).flatmap(
    lambda prefix: st.from_regex(r"[A-Za-z0-9]{36}", fullmatch=True).map(
        lambda suffix: prefix + suffix
    )
)

private_keys = safe_text.map(
    lambda body: (
        f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----"
    )
)

jwt_tokens = st.tuples(
    st.from_regex(r"[A-Za-z0-9_-]{10,30}", fullmatch=True),
    st.from_regex(r"[A-Za-z0-9_-]{10,30}", fullmatch=True),
).map(lambda parts: f"eyJhbGciOiJIUzI1NiJ9.eyJ{parts[0]}.{parts[1]}")

connection_strings = st.tuples(
    st.sampled_from(["postgres", "mysql", "mongodb", "redis", "amqp"]),
    st.from_regex(r"[a-z]{3,8}", fullmatch=True),
    st.from_regex(r"[a-zA-Z0-9]{4,12}", fullmatch=True),
    st.from_regex(r"[a-z]{3,10}", fullmatch=True),
).map(lambda t: f"{t[0]}://{t[1]}:{t[2]}@{t[3]}.example.com/db")

sensitive_var_assignments = st.tuples(
    st.sampled_from(["password", "secret", "key", "token", "auth"]),
    st.from_regex(r"[A-Za-z0-9]{8,20}", fullmatch=True),
).map(lambda t: f"{t[0]}={t[1]}")


@st.composite
def _embed(draw: st.DrawFn, secret_st: st.SearchStrategy[str]) -> str:
    """Embed a specific secret type into surrounding text."""
    prefix = draw(safe_text)
    secret = draw(secret_st)
    suffix = draw(safe_text)
    return f"{prefix} {secret} {suffix}"


# --- Property 17: Secret redaction in log output ---


@given(text=_embed(aws_keys), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_aws_keys(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing AWS access keys should have them redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    assert not re.search(r"AKIA[0-9A-Z]{16}", redacted)


@given(text=_embed(github_tokens), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_github_tokens(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing GitHub tokens should have them redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    assert not re.search(r"gh[pousr]_[A-Za-z0-9_]{20,}", redacted)


@given(text=_embed(private_keys), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_private_keys(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing private key blocks should have them redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    assert "PRIVATE KEY-----" not in redacted


@given(text=_embed(jwt_tokens), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_jwt_tokens(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing JWT tokens should have them redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    assert not re.search(
        r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", redacted
    )


@given(text=_embed(connection_strings), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_connection_strings(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing connection strings with passwords should have them redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    assert not re.search(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^:\s]+:[^@\s]+@[^\s]+", redacted)


@given(text=_embed(sensitive_var_assignments), cid=correlation_ids)
@settings(max_examples=100)
def test_redact_removes_sensitive_variable_values(text: str, cid: str) -> None:
    """**Validates: Requirements 7.5, 8.6**

    Strings containing password/secret/key/token/auth variable assignments
    should have the values redacted.
    """
    logger = StructuredLogger(cid)
    redacted = logger.redact(text)
    match = re.search(
        r"(?i)(?:password|secret|key|token|auth)\s*[:=]\s*(\S+)", redacted
    )
    if match:
        assert match.group(1) == "[REDACTED]"


@given(
    message=safe_text,
    cid=correlation_ids,
    secret=st.one_of(aws_keys, github_tokens, jwt_tokens, connection_strings),
    level=log_levels,
)
@settings(max_examples=100)
def test_log_output_contains_no_raw_secrets(
    message: str, cid: str, secret: str, level: str
) -> None:
    """**Validates: Requirements 7.5, 8.6**

    The JSON log output should not contain raw secret values passed in the message.
    """
    logger = StructuredLogger(cid)
    log_line = logger.log(level, f"{message} {secret}")
    assert secret not in log_line


# --- Property 18: Structured JSON log output ---


@given(message=safe_text, cid=correlation_ids, level=log_levels)
@settings(max_examples=100)
def test_log_output_is_valid_json(message: str, cid: str, level: str) -> None:
    """**Validates: Requirements 7.4**

    Every log call produces valid JSON output.
    """
    logger = StructuredLogger(cid)
    log_line = logger.log(level, message)
    parsed = json.loads(log_line)
    assert isinstance(parsed, dict)


@given(message=safe_text, cid=correlation_ids, level=log_levels)
@settings(max_examples=100)
def test_log_output_has_required_fields(message: str, cid: str, level: str) -> None:
    """**Validates: Requirements 7.4**

    Log output contains correlation_id, level, message, and timestamp fields.
    """
    logger = StructuredLogger(cid)
    log_line = logger.log(level, message)
    parsed = json.loads(log_line)

    assert "correlation_id" in parsed
    assert "level" in parsed
    assert "message" in parsed
    assert "timestamp" in parsed
    assert parsed["correlation_id"] == cid
    assert parsed["level"] == level


@given(message=safe_text, cid=correlation_ids, level=log_levels)
@settings(max_examples=100)
def test_log_output_timestamp_is_iso_format(message: str, cid: str, level: str) -> None:
    """**Validates: Requirements 7.4**

    The timestamp field is a valid ISO 8601 string.
    """
    from datetime import datetime

    logger = StructuredLogger(cid)
    log_line = logger.log(level, message)
    parsed = json.loads(log_line)
    datetime.fromisoformat(parsed["timestamp"])


@given(
    cid=correlation_ids,
    level=log_levels,
    message=safe_text,
    extra_key=st.from_regex(r"[a-z_]{2,10}", fullmatch=True),
    extra_val=safe_text,
)
@settings(max_examples=100)
def test_log_output_includes_extra_context(
    cid: str, level: str, message: str, extra_key: str, extra_val: str
) -> None:
    """**Validates: Requirements 7.4**

    Extra keyword arguments are included in the log output.
    """
    logger = StructuredLogger(cid)
    log_line = logger.log(level, message, **{extra_key: extra_val})
    parsed = json.loads(log_line)
    assert extra_key in parsed
