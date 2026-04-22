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
    remediation: str = ""  # Actionable fix suggestion from AI


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


# Webex API Registry models (kept for backward compat with AIModelClient prompt)


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


# Webex Ecosystem Catalog models


class SignalType(Enum):
    """Type of Webex ecosystem integration signal detected in code."""

    SDK_IMPORT = "sdk_import"
    REST_API_URL = "rest_api_url"
    WIDGET_MANIFEST = "widget_manifest"
    BYOVA_PATTERN = "byova_pattern"
    FLOW_REFERENCE = "flow_reference"
    MCP_REFERENCE = "mcp_reference"


@dataclass
class SDKPackageEntry:
    """A recognized Webex SDK package in the ecosystem catalog."""

    name: str  # Package name (e.g., "webex-js-sdk", "@webex/embedded-app-sdk")
    language: str  # Programming language (e.g., "javascript", "python")
    import_patterns: list[str]  # Regex patterns to detect imports
    technology: str  # Webex technology category (e.g., "Messaging", "Contact Center")


@dataclass
class RESTEndpointEntry:
    """A documented Webex Developer Platform REST API endpoint."""

    path: str  # API path (e.g., "/v1/messages")
    method: str  # HTTP method (GET, POST, etc.)
    technology: str  # Webex technology category
    description: str


@dataclass
class ManifestPattern:
    """A recognized Agent Desktop widget layout pattern."""

    pattern_type: str  # e.g., "agent_desktop_layout"
    detection_keys: list[
        str
    ]  # JSON keys that identify this layout (e.g., ["area", "comp"])
    technology: str  # Webex technology category
    description: str


@dataclass
class IntegrationPattern:
    """A recognized BYOVA, Flow, or MCP integration pattern."""

    pattern_type: str  # e.g., "byova_grpc", "connect_flow", "mcp_tool"
    detection_patterns: list[str]  # Regex patterns to detect in code
    technology: str  # Webex technology category
    description: str


@dataclass
class WebexEcosystemCatalog:
    """Complete catalog of recognized Webex Developer ecosystem integration signals."""

    sdk_packages: list[SDKPackageEntry] = field(default_factory=list)
    rest_endpoints: list[RESTEndpointEntry] = field(default_factory=list)
    manifest_patterns: list[ManifestPattern] = field(default_factory=list)
    integration_patterns: list[IntegrationPattern] = field(default_factory=list)


@dataclass
class EcosystemSignal:
    """A Webex ecosystem integration signal detected in scaffold code."""

    signal_type: SignalType
    file_path: str
    line_number: int
    matched_value: str  # The actual matched text (import statement, URL, etc.)
    technology: str  # Webex technology category (if identifiable)
    catalog_entry: str  # Reference to the catalog entry that matched (if any)
