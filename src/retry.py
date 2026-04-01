"""Retry decorator with configurable exponential backoff and jitter."""

import functools
import random
import time
from typing import Any, Callable


def with_retry(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator for retry with exponential backoff and jitter.

    Args:
        max_retries: Maximum number of retry attempts (not counting the initial call).
        backoff_base: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types that trigger a retry.

    Delay formula: min(backoff_base * (2 ** attempt) + random.uniform(0, 1), max_delay)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_error = exc
                    if attempt == max_retries:
                        raise
                    delay = min(
                        backoff_base * (2**attempt) + random.uniform(0, 1),
                        max_delay,
                    )
                    time.sleep(delay)
            # Unreachable, but satisfies type checker
            raise last_error  # type: ignore[misc]

        return wrapper

    return decorator
