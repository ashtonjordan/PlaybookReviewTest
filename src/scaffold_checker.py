"""ScaffoldChecker: Validates structural completeness of scaffolds.

Checks that a scaffold is structurally complete and runnable by verifying
the presence of entry points, dependency manifests, externalized configuration,
and absence of obvious syntax issues or incomplete code blocks.
"""

import os
import re

from src.models import Finding, PRFile, Severity

# File extensions considered as code files for syntax checking
_CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".go",
        ".rb",
        ".rs",
        ".cpp",
        ".c",
        ".cs",
        ".kt",
        ".swift",
        ".sh",
        ".bash",
        ".php",
        ".scala",
        ".groovy",
    }
)

# Entry point patterns by language
_ENTRY_POINT_PATTERNS: list[re.Pattern[str]] = [
    # Python
    re.compile(r'if\s+__name__\s*==\s*["\']__main__["\']'),
    re.compile(r"def\s+main\s*\("),
    re.compile(r"def\s+handler\s*\("),
    # JavaScript / TypeScript
    re.compile(r"module\.exports"),
    re.compile(r"export\s+default"),
    re.compile(r"exports\.handler"),
    # Java
    re.compile(r"public\s+static\s+void\s+main"),
    # Go
    re.compile(r"func\s+main\s*\("),
    # Shell shebang
    re.compile(r"^#!", re.MULTILINE),
]

# Filenames that indicate an entry point (without extension)
_ENTRY_POINT_BASENAMES: frozenset[str] = frozenset(
    {"main", "index", "app", "server", "handler"}
)

# Recognized dependency manifest filenames
_DEPENDENCY_MANIFESTS: frozenset[str] = frozenset(
    {
        "package.json",
        "requirements.txt",
        "Pipfile",
        "pyproject.toml",
        "pom.xml",
        "build.gradle",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "composer.json",
    }
)

# IP addresses considered safe (loopback / any-interface)
_SAFE_IPS: frozenset[str] = frozenset({"127.0.0.1", "0.0.0.0"})

# Hostnames considered safe in URL patterns
_SAFE_HOSTNAMES: frozenset[str] = frozenset(
    {"localhost", "example.com", "www.example.com", "test.example.com"}
)

# Documentation and well-known service hostnames that should not be flagged
# as hardcoded configuration (these are reference URLs, not connection params)
_DOCUMENTATION_HOSTNAMES: frozenset[str] = frozenset(
    {
        # Documentation sites
        "docs.python.org",
        "docs.oracle.com",
        "docs.microsoft.com",
        "learn.microsoft.com",
        "developer.mozilla.org",
        "developer.apple.com",
        "developer.android.com",
        "developer.webex.com",
        "developer.cisco.com",
        "cloud.google.com",
        "developers.google.com",
        "google-auth.readthedocs.io",
        "readthedocs.io",
        "readthedocs.org",
        "docs.aws.amazon.com",
        "docs.github.com",
        "help.webex.com",
        # Well-known OAuth / auth provider endpoints (standard, not configurable)
        "accounts.google.com",
        "oauth2.googleapis.com",
        "www.googleapis.com",
        "login.microsoftonline.com",
        "cognito-idp.amazonaws.com",
        "token.actions.githubusercontent.com",
        # Package registries
        "pypi.org",
        "npmjs.com",
        "www.npmjs.com",
        "registry.npmjs.org",
        "crates.io",
        "rubygems.org",
        "maven.org",
        # Standards / specs
        "tools.ietf.org",
        "www.w3.org",
        "json-schema.org",
        "yaml.org",
        "semver.org",
        # GitHub
        "github.com",
        "raw.githubusercontent.com",
        "api.github.com",
    }
)

# Pattern to detect non-loopback private IP addresses in code
_PRIVATE_IP_PATTERN: re.Pattern[str] = re.compile(
    r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"
)

# Pattern to detect hardcoded port numbers in URL-like patterns (e.g., :8080)
_PORT_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://[^\s\"'`]*|localhost|[\w.-]+):(\d{2,5})\b"
)

# Pattern to detect hardcoded hostnames in URL patterns
_HOSTNAME_URL_PATTERN: re.Pattern[str] = re.compile(
    r"https?://([a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+)"
)

# Bracket/brace/paren pairs for simple counting
_OPEN_BRACKETS: str = "({["
_CLOSE_BRACKETS: str = ")}]"

# Patterns indicating incomplete code
_TODO_PATTERN: re.Pattern[str] = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)

# Placeholder patterns indicating stub/incomplete code
_PLACEHOLDER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"pass\s*#\s*TODO", re.IGNORECASE),
    re.compile(r"raise\s+NotImplementedError"),
    # Ellipsis as function body — match lines that are just "..."
    re.compile(r"^\s*\.\.\.\s*$", re.MULTILINE),
]


class ScaffoldChecker:
    """Checks that a scaffold is structurally complete and runnable."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_entry_point(self, files: list[PRFile]) -> Finding | None:
        """Check for an identifiable entry point (main function, handler, script).

        Scans all files for language-specific entry point patterns and
        well-known entry point filenames (main.*, index.*, app.*, server.*,
        handler.*).

        Returns a Finding with severity ERROR if no entry point is found,
        or None if at least one entry point is detected.
        """
        for pr_file in files:
            # Check well-known entry point filenames
            basename = os.path.basename(pr_file.filename)
            name_without_ext = os.path.splitext(basename)[0].lower()
            if name_without_ext in _ENTRY_POINT_BASENAMES:
                return None

            # Check code content for entry point patterns
            code = pr_file.patch or ""
            for pattern in _ENTRY_POINT_PATTERNS:
                if pattern.search(code):
                    return None

        return Finding(
            file_path="",
            line_start=0,
            line_end=0,
            rule_id="scaffold-missing-entry-point",
            category="framework-security",
            severity=Severity.ERROR,
            description=(
                "No identifiable entry point found in the scaffold. "
                "Expected one of: a main function, an exported handler, "
                "a runnable script with a shebang, or a file named "
                "main/index/app/server/handler."
            ),
        )

    def check_dependency_manifest(self, files: list[PRFile]) -> Finding | None:
        """Check for a dependency manifest file.

        Looks for recognized dependency manifest filenames such as
        package.json, requirements.txt, pom.xml, etc. Checks both
        root-level and subdirectory paths.

        Returns a Finding with severity WARNING if no manifest is found,
        or None if at least one manifest is detected.
        """
        for pr_file in files:
            basename = os.path.basename(pr_file.filename)
            if basename in _DEPENDENCY_MANIFESTS:
                return None

        return Finding(
            file_path="",
            line_start=0,
            line_end=0,
            rule_id="scaffold-missing-dependency-manifest",
            category="supply-chain",
            severity=Severity.WARNING,
            description=(
                "No dependency manifest found in the scaffold. "
                "Expected one of: package.json, requirements.txt, Pipfile, "
                "pyproject.toml, pom.xml, build.gradle, Cargo.toml, go.mod, "
                "Gemfile, or composer.json."
            ),
        )

    def check_config_references(self, files: list[PRFile]) -> list[Finding]:
        """Check for hardcoded connection parameters in code files.

        Scans patch content for hardcoded IP addresses (excluding 127.0.0.1
        and 0.0.0.0), hardcoded port numbers in URL-like patterns, and
        hardcoded hostnames in URL patterns (excluding localhost, example.com,
        documentation sites, well-known auth providers, and URLs in comments).

        Returns a list of Findings with severity WARNING for each hardcoded
        reference found.
        """
        findings: list[Finding] = []

        for pr_file in files:
            if not self._is_code_file(pr_file.filename):
                continue

            code = pr_file.patch or ""
            lines = code.splitlines()

            for line_idx, line in enumerate(lines, start=1):
                # Skip comment lines — documentation URLs are not config
                stripped = line.lstrip()
                if (
                    stripped.startswith("#")
                    or stripped.startswith("//")
                    or stripped.startswith("*")
                    or stripped.startswith("/*")
                ):
                    continue

                findings.extend(
                    self._check_line_for_hardcoded_config(
                        line, line_idx, pr_file.filename
                    )
                )

        return findings

    def check_syntax(self, files: list[PRFile]) -> list[Finding]:
        """Check for obvious syntax issues in code files.

        Detects:
        - Unmatched brackets/braces/parentheses (simple counting)
        - TODO, FIXME, HACK, XXX comments indicating incomplete code
        - Placeholder patterns (pass # TODO, raise NotImplementedError,
          ellipsis as function body)

        Only scans files with recognized code extensions.

        Returns a list of Findings with severity WARNING for each issue.
        """
        findings: list[Finding] = []

        for pr_file in files:
            if not self._is_code_file(pr_file.filename):
                continue

            code = pr_file.patch or ""

            # Check for unmatched brackets
            bracket_finding = self._check_unmatched_brackets(code, pr_file.filename)
            if bracket_finding:
                findings.append(bracket_finding)

            # Check for TODO/FIXME/HACK/XXX comments and placeholder patterns
            findings.extend(self._check_incomplete_code(code, pr_file.filename))

        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_code_file(filename: str) -> bool:
        """Return True if the filename has a recognized code extension."""
        _, ext = os.path.splitext(filename)
        return ext.lower() in _CODE_EXTENSIONS

    @staticmethod
    def _check_line_for_hardcoded_config(
        line: str, line_number: int, filename: str
    ) -> list[Finding]:
        """Check a single line for hardcoded connection parameters."""
        findings: list[Finding] = []

        # Check for hardcoded IP addresses (skip safe ones)
        for match in _PRIVATE_IP_PATTERN.finditer(line):
            ip = match.group(1)
            if ip in _SAFE_IPS:
                continue
            # Validate it looks like a real IP (each octet 0-255)
            octets = ip.split(".")
            if all(0 <= int(o) <= 255 for o in octets):
                findings.append(
                    Finding(
                        file_path=filename,
                        line_start=line_number,
                        line_end=line_number,
                        rule_id="scaffold-hardcoded-config",
                        category="data-storage",
                        severity=Severity.WARNING,
                        description=(
                            f"Hardcoded IP address '{ip}' found. "
                            f"Consider using environment variables or "
                            f"configuration files for connection parameters."
                        ),
                    )
                )

        # Check for hardcoded port numbers in URL-like patterns
        for match in _PORT_PATTERN.finditer(line):
            port_str = match.group(1)
            full_match = match.group(0)
            # Skip if the host part is localhost or a safe hostname
            if any(
                safe in full_match.lower()
                for safe in ("localhost", "127.0.0.1", "0.0.0.0")
            ):
                continue
            # Skip well-known standard ports that aren't connection config
            well_known_ports = {"22", "80", "443"}
            if port_str in well_known_ports:
                continue
            findings.append(
                Finding(
                    file_path=filename,
                    line_start=line_number,
                    line_end=line_number,
                    rule_id="scaffold-hardcoded-config",
                    category="data-storage",
                    severity=Severity.WARNING,
                    description=(
                        f"Hardcoded port ':{port_str}' found in URL-like pattern. "
                        f"Consider using environment variables or "
                        f"configuration files for connection parameters."
                    ),
                )
            )

        # Check for hardcoded hostnames in URL patterns
        for match in _HOSTNAME_URL_PATTERN.finditer(line):
            hostname = match.group(1).lower()
            # Skip safe hostnames
            if hostname in _SAFE_HOSTNAMES:
                continue
            # Skip common safe patterns
            if hostname.endswith(".example.com") or hostname.endswith(".test"):
                continue
            # Skip documentation and well-known service hostnames
            if hostname in _DOCUMENTATION_HOSTNAMES:
                continue
            # Skip if any parent domain is in the documentation list
            # (e.g., "foo.readthedocs.io" matches "readthedocs.io")
            parts = hostname.split(".")
            skip = False
            for i in range(1, len(parts)):
                parent = ".".join(parts[i:])
                if parent in _DOCUMENTATION_HOSTNAMES:
                    skip = True
                    break
            if skip:
                continue
            findings.append(
                Finding(
                    file_path=filename,
                    line_start=line_number,
                    line_end=line_number,
                    rule_id="scaffold-hardcoded-config",
                    category="data-storage",
                    severity=Severity.WARNING,
                    description=(
                        f"Hardcoded hostname '{hostname}' found in URL. "
                        f"Consider using environment variables or "
                        f"configuration files for connection parameters."
                    ),
                )
            )

        return findings

    @staticmethod
    def _check_unmatched_brackets(code: str, filename: str) -> Finding | None:
        """Check for unmatched brackets/braces/parentheses via simple counting.

        Counts opening and closing brackets across the entire file content,
        skipping diff markers (+/-/@@) and content inside strings.
        Allows a small tolerance (±3) for large files since diff patches
        may not contain the complete file.
        Returns a Finding only for significant mismatches.
        """
        counts: dict[str, int] = {"(": 0, ")": 0, "{": 0, "}": 0, "[": 0, "]": 0}
        in_string = False
        string_char = ""
        prev_char = ""

        for line in code.splitlines():
            # Skip diff markers
            stripped = line.lstrip()
            if (
                stripped.startswith("@@")
                or stripped.startswith("---")
                or stripped.startswith("+++")
            ):
                continue
            # Strip diff prefix (+/-) before counting
            if line.startswith("+") or line.startswith("-"):
                line = line[1:]

            for char in line:
                if char in ('"', "'") and prev_char != "\\":
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                elif not in_string and char in counts:
                    counts[char] += 1
                prev_char = char

        # Allow a tolerance of ±3 for diff patches that may be incomplete
        tolerance = 3
        mismatches: list[str] = []
        pairs = [("(", ")"), ("{", "}"), ("[", "]")]
        for open_b, close_b in pairs:
            diff = abs(counts[open_b] - counts[close_b])
            if diff > tolerance:
                mismatches.append(
                    f"'{open_b}{close_b}' ({counts[open_b]} open, {counts[close_b]} close)"
                )

        if mismatches:
            return Finding(
                file_path=filename,
                line_start=1,
                line_end=1,
                rule_id="scaffold-syntax-issue",
                category="framework-security",
                severity=Severity.WARNING,
                description=(
                    f"Unmatched brackets detected: {', '.join(mismatches)}. "
                    f"This may indicate incomplete or malformed code."
                ),
            )
        return None

    @staticmethod
    def _check_incomplete_code(code: str, filename: str) -> list[Finding]:
        """Check for TODO/FIXME/HACK/XXX comments and placeholder patterns."""
        findings: list[Finding] = []
        lines = code.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            # Check for TODO/FIXME/HACK/XXX markers
            todo_match = _TODO_PATTERN.search(line)
            if todo_match:
                marker = todo_match.group(1).upper()
                findings.append(
                    Finding(
                        file_path=filename,
                        line_start=line_idx,
                        line_end=line_idx,
                        rule_id="scaffold-syntax-issue",
                        category="framework-security",
                        severity=Severity.WARNING,
                        description=(
                            f"'{marker}' comment found, indicating incomplete code."
                        ),
                    )
                )

            # Check for placeholder patterns
            for placeholder_pattern in _PLACEHOLDER_PATTERNS:
                if placeholder_pattern.search(line):
                    findings.append(
                        Finding(
                            file_path=filename,
                            line_start=line_idx,
                            line_end=line_idx,
                            rule_id="scaffold-syntax-issue",
                            category="framework-security",
                            severity=Severity.WARNING,
                            description=(
                                "Placeholder or stub code detected, indicating "
                                "incomplete implementation."
                            ),
                        )
                    )
                    break  # One placeholder finding per line is enough

        return findings
