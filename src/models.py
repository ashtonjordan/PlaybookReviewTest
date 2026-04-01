"""Data models for the GitHub PR Review Agent."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(Enum):
    """Severity levels for review findings."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


VALID_CATEGORIES = frozenset(
    {
        "hardcoded-credentials",
        "api-security",
        "authentication",
        "input-validation",
        "logging",
        "authorization",
        "supply-chain",
        "framework-security",
        "data-storage",
        "privacy",
        "devops-containers",
        # Extended categories from CodeGuard source tags
        "data-security",
        "secrets",
        "web",
        "crypto",
        "mobile",
        "cloud",
        "iac",
        "mcp",
        "general",
    }
)

# Maps CodeGuard frontmatter tags to our category values.
# A source file may have multiple tags; the first match wins.
CODEGUARD_TAG_TO_CATEGORY: dict[str, str] = {
    "data-security": "data-security",
    "secrets": "secrets",
    "web": "web",
    "crypto": "crypto",
    "mobile": "mobile",
    "cloud": "cloud",
    "iac": "iac",
    "mcp": "mcp",
}


@dataclass
class Rule:
    """A single review rule derived from CodeGuard steering files."""

    id: str
    category: str
    description: str
    severity: Severity
    prompt_or_pattern: str
    enabled: bool = True
    languages: list[str] = field(default_factory=list)  # From CodeGuard frontmatter
    tags: list[str] = field(default_factory=list)  # From CodeGuard frontmatter


@dataclass
class RuleSet:
    """Collection of review rules with optional file allowlist override."""

    rules: list[Rule]
    version: str = "1.0"
    file_allowlist: list[str] = field(default_factory=list)


@dataclass
class PRFile:
    """A file changed in a pull request."""

    filename: str
    status: str  # added, modified, removed
    additions: int
    deletions: int
    patch: str


@dataclass
class FileDiff:
    """Processed diff for AI analysis (after allowlist filtering)."""

    filename: str
    patch: str
    language: Optional[str]


@dataclass
class Finding:
    """A single review finding."""

    file_path: str
    line_start: int
    line_end: int
    rule_id: str
    category: str
    severity: Severity
    description: str


@dataclass
class ReviewReport:
    """Structured review report with verdict and findings."""

    verdict: str  # "pass" or "fail"
    findings: list[Finding]
    summary: dict[str, int]  # Severity -> count mapping
    correlation_id: str

    @property
    def has_errors(self) -> bool:
        """Return True if any finding has severity ERROR."""
        return any(f.severity == Severity.ERROR for f in self.findings)


@dataclass
class ReviewComment:
    """A review comment to post on GitHub."""

    file_path: str
    line: int
    body: str


# Webex API Registry models


@dataclass
class WebexEndpoint:
    """A documented Webex Developer Platform API endpoint."""

    path: str
    method: str
    technology: str
    description: str


@dataclass
class WebexAPIRegistryData:
    """Collection of documented Webex API endpoints."""

    endpoints: list[WebexEndpoint]


@dataclass
class APIReference:
    """An API reference extracted from scaffold code."""

    path: str
    method: Optional[str]
    file_path: str
    line_number: int
