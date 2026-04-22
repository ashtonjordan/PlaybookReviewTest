"""WebexEcosystemDetector: Tier 1 signal detection for Webex ecosystem integrations.

Scans scaffold code files for Webex Developer ecosystem integration signals
including SDK imports, REST API URLs, widget manifests, BYOVA/Flow patterns,
and MCP tool references. Uses the Webex_Ecosystem_Catalog to match known
patterns and reports findings for missing or unused integrations.
"""

import json
import re

from src.models import (
    EcosystemSignal,
    Finding,
    IntegrationPattern,
    PRFile,
    Severity,
    SignalType,
    WebexEcosystemCatalog,
)

# Built-in URL patterns for Webex REST API detection (always checked)
_REST_API_URL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"https?://[^\s\"'`]*webexapis\.com[^\s\"'`]*", re.IGNORECASE),
    re.compile(r"https?://[^\s\"'`]*api\.ciscospark\.com[^\s\"'`]*", re.IGNORECASE),
]


class WebexEcosystemDetector:
    """Detects Webex ecosystem integration signals in scaffold code (Tier 1)."""

    def __init__(self, catalog: WebexEcosystemCatalog):
        self._catalog = catalog
        # Pre-compile SDK import patterns from the catalog
        self._compiled_sdk_patterns: list[
            tuple[re.Pattern[str], str, str]
        ] = []  # (pattern, sdk_name, technology)
        for pkg in catalog.sdk_packages:
            for pat_str in pkg.import_patterns:
                try:
                    compiled = re.compile(pat_str)
                    self._compiled_sdk_patterns.append(
                        (compiled, pkg.name, pkg.technology)
                    )
                except re.error:
                    continue

        # Pre-compile integration patterns grouped by type
        self._byova_patterns: list[tuple[re.Pattern[str], IntegrationPattern]] = []
        self._connect_flow_patterns: list[
            tuple[re.Pattern[str], IntegrationPattern]
        ] = []
        self._mcp_patterns: list[tuple[re.Pattern[str], IntegrationPattern]] = []

        for ip in catalog.integration_patterns:
            target: list[tuple[re.Pattern[str], IntegrationPattern]]
            if ip.pattern_type == "byova_grpc":
                target = self._byova_patterns
            elif ip.pattern_type == "connect_flow":
                target = self._connect_flow_patterns
            elif ip.pattern_type == "mcp_tool":
                target = self._mcp_patterns
            else:
                continue
            for pat_str in ip.detection_patterns:
                try:
                    compiled = re.compile(pat_str)
                    target.append((compiled, ip))
                except re.error:
                    continue

    # ------------------------------------------------------------------
    # Public API — Combined Validation
    # ------------------------------------------------------------------

    def validate(self, files: list[PRFile]) -> list[Finding]:
        """Run full two-tier validation on PR files.

        1. Detect all ecosystem signals (Tier 1).
        2. If no signals found, return an error finding.
        3. If signals found, check SDK usage and validate REST endpoints (Tier 2).
        Returns combined list of findings.
        """
        signals = self.detect_signals(files)

        if not signals:
            return [
                Finding(
                    file_path="",
                    line_start=0,
                    line_end=0,
                    rule_id="ecosystem-no-webex-integration",
                    category="api-security",
                    severity=Severity.ERROR,
                    description=(
                        "No Webex Developer ecosystem integration detected in "
                        "scaffold code. Expected at least one of: SDK import, "
                        "REST API URL, widget manifest, BYOVA pattern, or MCP "
                        "reference."
                    ),
                )
            ]

        findings: list[Finding] = []

        # Tier 2a: Check SDK import-only usage
        # Group SDK signals by file_path, then check usage against each file's code
        sdk_signals = [s for s in signals if s.signal_type == SignalType.SDK_IMPORT]
        if sdk_signals:
            # Build a map of filename -> patch content from the PR files
            file_code_map: dict[str, str] = {f.filename: (f.patch or "") for f in files}
            # Group SDK signals by file path
            sdk_by_file: dict[str, list[EcosystemSignal]] = {}
            for sig in sdk_signals:
                sdk_by_file.setdefault(sig.file_path, []).append(sig)

            for file_path, file_sdk_signals in sdk_by_file.items():
                code = file_code_map.get(file_path, "")
                findings.extend(self.check_sdk_usage(code, file_sdk_signals))

        # Tier 2b: Validate REST API endpoints against catalog
        rest_signals = [s for s in signals if s.signal_type == SignalType.REST_API_URL]
        if rest_signals:
            findings.extend(self.validate_rest_endpoints(rest_signals))

        return findings

    # ------------------------------------------------------------------
    # Public API — Tier 1 Signal Detection
    # ------------------------------------------------------------------

    def detect_signals(self, files: list[PRFile]) -> list[EcosystemSignal]:
        """Scan code files for all Webex ecosystem integration signals.

        Calls each sub-detector and aggregates results. The caller (ReviewAgent)
        is responsible for file filtering via the File_Allowlist; this method
        evaluates every file it receives.
        """
        signals: list[EcosystemSignal] = []

        for pr_file in files:
            code = pr_file.patch or ""
            filename = pr_file.filename

            signals.extend(self.detect_sdk_imports(code, filename))
            signals.extend(self.detect_rest_api_urls(code, filename))
            signals.extend(self.detect_byova_patterns(code, filename))
            signals.extend(self.detect_mcp_references(code, filename))

        # Widget manifests need the full file list (they inspect JSON structure)
        signals.extend(self.detect_widget_manifests(files))

        return signals

    def detect_sdk_imports(self, code: str, filename: str) -> list[EcosystemSignal]:
        """Detect recognized Webex SDK import statements in code.

        Matches against regex patterns from the catalog's sdk_packages entries.
        Stores the full line as matched_value so usage analysis can extract
        imported names (e.g., ``from webexteamssdk import WebexTeamsAPI``).
        """
        signals: list[EcosystemSignal] = []
        lines = code.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            for pattern, sdk_name, technology in self._compiled_sdk_patterns:
                match = pattern.search(line)
                if match:
                    signals.append(
                        EcosystemSignal(
                            signal_type=SignalType.SDK_IMPORT,
                            file_path=filename,
                            line_number=line_idx,
                            matched_value=line.strip(),
                            technology=technology,
                            catalog_entry=sdk_name,
                        )
                    )
        return signals

    def detect_rest_api_urls(self, code: str, filename: str) -> list[EcosystemSignal]:
        """Detect REST API URL patterns (webexapis.com, api.ciscospark.com) in code.

        Uses built-in URL patterns that are always checked regardless of catalog
        content. The catalog's rest_endpoints are used later in Tier 2 validation.
        """
        signals: list[EcosystemSignal] = []
        lines = code.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            for url_pattern in _REST_API_URL_PATTERNS:
                for match in url_pattern.finditer(line):
                    signals.append(
                        EcosystemSignal(
                            signal_type=SignalType.REST_API_URL,
                            file_path=filename,
                            line_number=line_idx,
                            matched_value=match.group(0),
                            technology="Webex REST API",
                            catalog_entry="",
                        )
                    )
        return signals

    def detect_widget_manifests(self, files: list[PRFile]) -> list[EcosystemSignal]:
        """Detect Agent Desktop layout JSON files with detection keys from the catalog.

        Parses JSON content from PRFile patches. If the parsed JSON contains ALL
        detection_keys from a ManifestPattern, it's a match.
        """
        signals: list[EcosystemSignal] = []

        if not self._catalog.manifest_patterns:
            return signals

        for pr_file in files:
            if not pr_file.filename.endswith(".json"):
                continue

            json_content = self._extract_json_from_patch(pr_file.patch or "")
            if json_content is None:
                continue

            for manifest in self._catalog.manifest_patterns:
                if not manifest.detection_keys:
                    continue
                if self._json_contains_all_keys(json_content, manifest.detection_keys):
                    signals.append(
                        EcosystemSignal(
                            signal_type=SignalType.WIDGET_MANIFEST,
                            file_path=pr_file.filename,
                            line_number=1,
                            matched_value=", ".join(manifest.detection_keys),
                            technology=manifest.technology,
                            catalog_entry=manifest.pattern_type,
                        )
                    )
        return signals

    def detect_byova_patterns(self, code: str, filename: str) -> list[EcosystemSignal]:
        """Detect BYOVA gRPC service definitions and Webex Connect flow references.

        Uses regex patterns from the catalog's integration_patterns where
        pattern_type is "byova_grpc" or "connect_flow".
        """
        signals: list[EcosystemSignal] = []
        lines = code.splitlines()

        all_patterns = self._byova_patterns + self._connect_flow_patterns

        for line_idx, line in enumerate(lines, start=1):
            for pattern, ip in all_patterns:
                match = pattern.search(line)
                if match:
                    signal_type = (
                        SignalType.BYOVA_PATTERN
                        if ip.pattern_type == "byova_grpc"
                        else SignalType.FLOW_REFERENCE
                    )
                    signals.append(
                        EcosystemSignal(
                            signal_type=signal_type,
                            file_path=filename,
                            line_number=line_idx,
                            matched_value=match.group(0),
                            technology=ip.technology,
                            catalog_entry=ip.pattern_type,
                        )
                    )
        return signals

    def detect_mcp_references(self, code: str, filename: str) -> list[EcosystemSignal]:
        """Detect MCP tool references for Webex services.

        Uses regex patterns from the catalog's integration_patterns where
        pattern_type is "mcp_tool".
        """
        signals: list[EcosystemSignal] = []
        lines = code.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            for pattern, ip in self._mcp_patterns:
                match = pattern.search(line)
                if match:
                    signals.append(
                        EcosystemSignal(
                            signal_type=SignalType.MCP_REFERENCE,
                            file_path=filename,
                            line_number=line_idx,
                            matched_value=match.group(0),
                            technology=ip.technology,
                            catalog_entry=ip.pattern_type,
                        )
                    )
        return signals

    def check_sdk_usage(
        self, code: str, sdk_signals: list[EcosystemSignal]
    ) -> list[Finding]:
        """Verify SDK imports are actually used beyond the import statement.

        For each detected SDK import signal, checks whether the imported package
        name (or common aliases) appears elsewhere in the code beyond the import
        line itself. Returns "warning" findings for import-only usage.
        """
        findings: list[Finding] = []
        if not sdk_signals:
            return findings

        lines = code.splitlines()

        for signal in sdk_signals:
            if signal.signal_type != SignalType.SDK_IMPORT:
                continue

            import_line_idx = signal.line_number - 1  # 0-based
            # Use the catalog entry (SDK name) and the matched value to derive
            # identifiers to search for in the rest of the code
            search_terms = self._derive_usage_terms(signal)

            used = False
            for idx, line in enumerate(lines):
                if idx == import_line_idx:
                    continue
                for term in search_terms:
                    if term in line:
                        used = True
                        break
                if used:
                    break

            if not used:
                findings.append(
                    Finding(
                        file_path=signal.file_path,
                        line_start=signal.line_number,
                        line_end=signal.line_number,
                        rule_id="ecosystem-sdk-import-only",
                        category="api-security",
                        severity=Severity.WARNING,
                        description=(
                            f"SDK '{signal.catalog_entry}' is imported but not used "
                            f"beyond the import statement. Detected import: "
                            f"'{signal.matched_value}'"
                        ),
                    )
                )
        return findings

    # ------------------------------------------------------------------
    # Tier 2: REST API Endpoint Validation
    # ------------------------------------------------------------------

    def validate_rest_endpoints(
        self, rest_signals: list[EcosystemSignal]
    ) -> list[Finding]:
        """Validate detected REST API URL signals against the catalog's REST endpoints.

        For each signal with signal_type=REST_API_URL, extracts the API endpoint
        path from the matched URL and checks whether it exists in the catalog's
        rest_endpoints list. Returns WARNING findings for undocumented endpoints.

        Path matching is case-insensitive and normalizes trailing slashes.
        """
        findings: list[Finding] = []
        if not rest_signals:
            return findings

        # Build a set of known paths (lowercased, no trailing slash) for fast lookup
        known_paths: set[str] = set()
        for ep in self._catalog.rest_endpoints:
            known_paths.add(ep.path.lower().rstrip("/"))

        for signal in rest_signals:
            if signal.signal_type != SignalType.REST_API_URL:
                continue

            extracted_path = self._extract_path_from_url(signal.matched_value)
            if not extracted_path:
                continue

            normalized = extracted_path.lower().rstrip("/")
            if normalized not in known_paths:
                findings.append(
                    Finding(
                        file_path=signal.file_path,
                        line_start=signal.line_number,
                        line_end=signal.line_number,
                        rule_id="ecosystem-undocumented-rest-endpoint",
                        category="api-security",
                        severity=Severity.WARNING,
                        description=(
                            f"REST API endpoint '{extracted_path}' is not documented "
                            f"in the Webex Ecosystem Catalog. "
                            f"Detected URL: '{signal.matched_value}'"
                        ),
                    )
                )
        return findings

    @staticmethod
    def _extract_path_from_url(url: str) -> str:
        """Extract the API endpoint path from a Webex REST API URL.

        For example, from "https://webexapis.com/v1/messages" extracts "/v1/messages".
        Returns an empty string if no path can be extracted.
        """
        # Match the host portion and capture everything after it as the path
        match = re.search(r"https?://[^/\s\"'`]+((?:/[^\s\"'`]*)?)", url, re.IGNORECASE)
        if not match:
            return ""
        path = match.group(1)
        # If no path segment was captured, the URL is just the host
        if not path:
            return "/"
        return path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json_from_patch(patch: str) -> object | None:
        """Try to parse JSON content from a PR file patch.

        Strips diff markers (+/-/@@) and attempts to parse the remaining
        content as JSON. Returns the parsed object or None on failure.
        """
        # Strip diff line prefixes to reconstruct the file content
        clean_lines: list[str] = []
        for line in patch.splitlines():
            if line.startswith("@@"):
                continue
            if line.startswith("+"):
                clean_lines.append(line[1:])
            elif line.startswith("-"):
                continue
            else:
                clean_lines.append(line)

        content = "\n".join(clean_lines).strip()
        if not content:
            return None

        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _json_contains_all_keys(obj: object, keys: list[str]) -> bool:
        """Recursively check if a JSON object contains ALL specified keys."""
        if isinstance(obj, dict):
            found_keys = set()
            for key in keys:
                if key in obj:
                    found_keys.add(key)
            # Also search nested structures
            for value in obj.values():
                nested_found = WebexEcosystemDetector._find_keys_in_json(value, keys)
                found_keys.update(nested_found)
            return all(k in found_keys for k in keys)
        if isinstance(obj, list):
            found_keys: set[str] = set()
            for item in obj:
                nested_found = WebexEcosystemDetector._find_keys_in_json(item, keys)
                found_keys.update(nested_found)
            return all(k in found_keys for k in keys)
        return False

    @staticmethod
    def _find_keys_in_json(obj: object, keys: list[str]) -> set[str]:
        """Recursively find which of the specified keys exist in a JSON structure."""
        found: set[str] = set()
        if isinstance(obj, dict):
            for key in keys:
                if key in obj:
                    found.add(key)
            for value in obj.values():
                found.update(WebexEcosystemDetector._find_keys_in_json(value, keys))
        elif isinstance(obj, list):
            for item in obj:
                found.update(WebexEcosystemDetector._find_keys_in_json(item, keys))
        return found

    @staticmethod
    def _derive_usage_terms(signal: EcosystemSignal) -> list[str]:
        """Derive search terms from an SDK import signal to check for actual usage.

        Extracts meaningful identifiers from the matched import value and
        catalog entry name that would indicate the SDK is being used beyond
        the import statement.
        """
        terms: list[str] = []
        matched = signal.matched_value
        catalog_name = signal.catalog_entry

        # Extract the imported module/package name from common import patterns
        # Python: "from X import Y" -> search for Y; "import X" -> search for X
        py_from_match = re.search(r"from\s+\S+\s+import\s+(.+)", matched)
        if py_from_match:
            imports = py_from_match.group(1)
            for part in imports.split(","):
                part = part.strip()
                # Handle "X as Y" aliases
                if " as " in part:
                    terms.append(part.split(" as ")[-1].strip())
                else:
                    terms.append(part.strip())
        else:
            py_import_match = re.search(r"import\s+(\S+)", matched)
            if py_import_match:
                module = py_import_match.group(1)
                # Handle "X as Y" aliases
                if " as " in matched:
                    alias_match = re.search(r"as\s+(\S+)", matched)
                    if alias_match:
                        terms.append(alias_match.group(1))
                terms.append(module.split(".")[-1])

        # JS/TS: require("X") or import X from "Y" -> search for X
        js_require = re.search(r"require\s*\(\s*['\"]([^'\"]+)", matched)
        if js_require:
            pkg = js_require.group(1)
            terms.append(pkg.split("/")[-1])

        js_import = re.search(r"import\s+(\w+)", matched)
        if js_import:
            terms.append(js_import.group(1))

        js_destructure = re.search(r"import\s*\{([^}]+)\}", matched)
        if js_destructure:
            for part in js_destructure.group(1).split(","):
                part = part.strip()
                if " as " in part:
                    terms.append(part.split(" as ")[-1].strip())
                else:
                    terms.append(part.strip())

        # Add the catalog entry name as a fallback search term
        if catalog_name:
            # Use the last segment of scoped packages (e.g., "@webex/sdk" -> "sdk")
            simple_name = catalog_name.split("/")[-1]
            terms.append(simple_name)

        # Filter out empty strings and very short terms that would false-positive
        return [t for t in terms if t and len(t) > 1]
