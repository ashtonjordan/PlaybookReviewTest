"""StructuredLogger — structured JSON logging with secret redaction and correlation ID tracking."""

import json
import re
import sys
from datetime import datetime, timezone


# Pre-compiled secret patterns for redaction
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    # AWS access keys (AKIA followed by 16 alphanumeric chars)
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # GitHub tokens (ghp_, ghs_, gho_, ghu_ followed by alphanumeric chars)
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    # Private key blocks
    (
        re.compile(
            r"-----BEGIN\s[\w\s]*PRIVATE\sKEY-----[\s\S]*?-----END\s[\w\s]*PRIVATE\sKEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # JWT tokens (three dot-separated base64url segments)
    (
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "[REDACTED_JWT]",
    ),
    # Connection strings with passwords (e.g. postgres://user:pass@host)
    (
        re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^:\s]+:[^@\s]+@[^\s]+"),
        "[REDACTED_CONNECTION_STRING]",
    ),
    # Variable assignments containing sensitive names
    (
        re.compile(
            r"""(?i)(["']?(?:password|secret|key|token|auth)["']?\s*[:=]\s*)(\S+)"""
        ),
        r"\1[REDACTED]",
    ),
]


class StructuredLogger:
    """Structured JSON logger with secret redaction and correlation ID tracking."""

    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id

    def log(self, level: str, message: str, **context: object) -> str:
        """Log a structured JSON message. Redacts secrets from all fields.

        Returns the JSON string that was written (useful for testing).
        """
        entry: dict[str, object] = {
            "correlation_id": self.correlation_id,
            "level": level,
            "message": self.redact(message),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for k, v in context.items():
            entry[k] = self._redact_value(v)

        line = json.dumps(entry, default=str)
        print(line, file=sys.stderr)
        return line

    def redact(self, value: str) -> str:
        """Redact known secret patterns from a string."""
        result = value
        for pattern, replacement in _SECRET_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def _redact_value(self, value: object) -> object:
        """Recursively redact secrets from any value."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {k: self._redact_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact_value(item) for item in value]
        return value
