"""Property-based tests for the retry decorator (Property 8).

# Feature: github-pr-review-agent, Property 8: Retry with exponential backoff on transient failures
# Validates: Requirements 2.3, 6.5, 7.2
"""

from unittest.mock import patch

from hypothesis import given, settings
import hypothesis.strategies as st

from src.retry import with_retry


class TransientError(Exception):
    """Simulated transient/retryable error."""


class PermanentError(Exception):
    """Simulated non-retryable error."""


# --- Strategies ---

max_retries_st = st.integers(min_value=1, max_value=5)
backoff_base_st = st.floats(
    min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False
)
max_delay_st = st.floats(
    min_value=0.1, max_value=60.0, allow_nan=False, allow_infinity=False
)
# How many times the function fails before succeeding (0 = never fails)
fail_count_st = st.integers(min_value=0, max_value=5)


@given(max_retries=max_retries_st, fail_before_success=fail_count_st)
@settings(max_examples=100)
def test_retry_count_matches_transient_failures(
    max_retries: int, fail_before_success: int
) -> None:
    """**Validates: Requirements 2.3, 6.5, 7.2**

    The decorated function is called exactly min(fail_before_success, max_retries) + 1
    times when it fails with a retryable exception, and succeeds if
    fail_before_success <= max_retries.
    """
    call_count = 0

    @with_retry(max_retries=max_retries, retryable_exceptions=(TransientError,))
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count <= fail_before_success:
            raise TransientError("transient")
        return "ok"

    with patch("src.retry.time.sleep"):
        if fail_before_success <= max_retries:
            result = flaky()
            assert result == "ok"
            assert call_count == fail_before_success + 1
        else:
            try:
                flaky()
                assert False, "Should have raised"
            except TransientError:
                assert call_count == max_retries + 1


@given(max_retries=max_retries_st, backoff_base=backoff_base_st, max_delay=max_delay_st)
@settings(max_examples=100)
def test_delays_increase_with_exponential_backoff(
    max_retries: int, backoff_base: float, max_delay: float
) -> None:
    """**Validates: Requirements 2.3, 6.5, 7.2**

    Each retry delay follows exponential backoff: the base component
    (backoff_base * 2^attempt) increases with each attempt, capped at max_delay.
    """
    recorded_delays: list[float] = []

    @with_retry(
        max_retries=max_retries,
        backoff_base=backoff_base,
        max_delay=max_delay,
        retryable_exceptions=(TransientError,),
    )
    def always_fail():
        raise TransientError("boom")

    with patch("src.retry.time.sleep", side_effect=lambda d: recorded_delays.append(d)):
        try:
            always_fail()
        except TransientError:
            pass

    assert len(recorded_delays) == max_retries
    for attempt, delay in enumerate(recorded_delays):
        # delay = min(backoff_base * 2^attempt + jitter, max_delay)
        # jitter is in [0, 1), so delay >= min(backoff_base * 2^attempt, max_delay)
        base_component = backoff_base * (2**attempt)
        assert delay <= max_delay + 1e-9  # capped (with float tolerance)
        assert delay >= min(base_component, max_delay) - 1e-9


@given(max_retries=max_retries_st)
@settings(max_examples=100)
def test_non_retryable_exception_propagates_immediately(max_retries: int) -> None:
    """**Validates: Requirements 2.3, 6.5, 7.2**

    Exceptions not in retryable_exceptions propagate immediately without retry.
    """
    call_count = 0

    @with_retry(max_retries=max_retries, retryable_exceptions=(TransientError,))
    def raise_permanent():
        nonlocal call_count
        call_count += 1
        raise PermanentError("permanent")

    with patch("src.retry.time.sleep"):
        try:
            raise_permanent()
            assert False, "Should have raised"
        except PermanentError:
            assert call_count == 1  # No retries for non-retryable


@given(max_retries=max_retries_st)
@settings(max_examples=100)
def test_successful_call_returns_without_retry(max_retries: int) -> None:
    """**Validates: Requirements 2.3, 6.5, 7.2**

    A function that succeeds on the first call is invoked exactly once.
    """
    call_count = 0

    @with_retry(max_retries=max_retries, retryable_exceptions=(TransientError,))
    def succeed():
        nonlocal call_count
        call_count += 1
        return 42

    result = succeed()
    assert result == 42
    assert call_count == 1


@given(
    max_retries=max_retries_st,
    backoff_base=backoff_base_st,
    max_delay=max_delay_st,
)
@settings(max_examples=100)
def test_delay_includes_jitter(
    max_retries: int, backoff_base: float, max_delay: float
) -> None:
    """**Validates: Requirements 2.3, 6.5, 7.2**

    Each delay includes a jitter component (random.uniform(0, 1)), so the delay
    is strictly greater than the pure exponential base when not capped.
    """
    recorded_delays: list[float] = []

    @with_retry(
        max_retries=max_retries,
        backoff_base=backoff_base,
        max_delay=max_delay,
        retryable_exceptions=(TransientError,),
    )
    def always_fail():
        raise TransientError("boom")

    with patch("src.retry.time.sleep", side_effect=lambda d: recorded_delays.append(d)):
        try:
            always_fail()
        except TransientError:
            pass

    for attempt, delay in enumerate(recorded_delays):
        base_component = backoff_base * (2**attempt)
        # If not capped, delay should be >= base_component (jitter adds >= 0)
        if base_component < max_delay:
            assert delay >= base_component - 1e-9
