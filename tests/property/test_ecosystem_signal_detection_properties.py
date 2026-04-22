"""Property-based tests for Webex ecosystem signal detection (Property 20).

# Feature: github-pr-review-agent, Property 20: Webex ecosystem signal detection (Tier 1)
# Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.13, 11.14
"""

import json

import hypothesis.strategies as st
from hypothesis import given, settings

from src.models import (
    EcosystemSignal,
    Finding,
    IntegrationPattern,
    ManifestPattern,
    PRFile,
    SDKPackageEntry,
    Severity,
    SignalType,
    WebexEcosystemCatalog,
)
from src.webex_ecosystem_detector import WebexEcosystemDetector

# ---------------------------------------------------------------------------
# Helper catalog for deterministic tests
# ---------------------------------------------------------------------------

# Known SDK packages used in the catalog
SDK_CATALOG_ENTRIES = [
    SDKPackageEntry(
        name="webexteamssdk",
        language="python",
        import_patterns=[r"import\s+webexteamssdk", r"from\s+webexteamssdk\s+import"],
        technology="Messaging",
    ),
    SDKPackageEntry(
        name="wxc_sdk",
        language="python",
        import_patterns=[r"import\s+wxc_sdk", r"from\s+wxc_sdk\s+import"],
        technology="Calling",
    ),
    SDKPackageEntry(
        name="webex-js-sdk",
        language="javascript",
        import_patterns=[
            r"""require\s*\(\s*['"]webex['"]""",
            r"""from\s+['"]webex['"]""",
        ],
        technology="Messaging",
    ),
    SDKPackageEntry(
        name="@webex/embedded-app-sdk",
        language="javascript",
        import_patterns=[r"""require\s*\(\s*['"]@webex/embedded-app-sdk['"]"""],
        technology="Embedded Apps",
    ),
]

# Known manifest patterns
MANIFEST_CATALOG_ENTRIES = [
    ManifestPattern(
        pattern_type="agent_desktop_layout",
        detection_keys=["area", "comp"],
        technology="Contact Center",
        description="Agent Desktop widget layout",
    ),
]

# Known integration (BYOVA) patterns
INTEGRATION_CATALOG_ENTRIES = [
    IntegrationPattern(
        pattern_type="byova_grpc",
        detection_patterns=[r"VoiceVirtualAgent", r"byova_common"],
        technology="Contact Center BYOVA",
        description="BYOVA gRPC service definition",
    ),
]


def _make_catalog(
    sdk: list[SDKPackageEntry] | None = None,
    manifests: list[ManifestPattern] | None = None,
    integrations: list[IntegrationPattern] | None = None,
) -> WebexEcosystemCatalog:
    """Build a catalog with sensible defaults for testing."""
    return WebexEcosystemCatalog(
        sdk_packages=sdk if sdk is not None else SDK_CATALOG_ENTRIES,
        rest_endpoints=[],
        manifest_patterns=manifests
        if manifests is not None
        else MANIFEST_CATALOG_ENTRIES,
        integration_patterns=integrations
        if integrations is not None
        else INTEGRATION_CATALOG_ENTRIES,
    )


def _make_detector(
    sdk: list[SDKPackageEntry] | None = None,
    manifests: list[ManifestPattern] | None = None,
    integrations: list[IntegrationPattern] | None = None,
) -> WebexEcosystemDetector:
    return WebexEcosystemDetector(_make_catalog(sdk, manifests, integrations))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Python SDK import lines
python_sdk_imports = st.sampled_from(
    [
        "import webexteamssdk",
        "from webexteamssdk import WebexTeamsAPI",
        "import wxc_sdk",
        "from wxc_sdk import WebexSimpleApi",
    ]
)

# JavaScript SDK import/require lines
js_sdk_imports = st.sampled_from(
    [
        "const webex = require('webex')",
        "const sdk = require('@webex/embedded-app-sdk')",
        "import webex from 'webex'",
    ]
)

all_sdk_imports = st.one_of(python_sdk_imports, js_sdk_imports)

# REST API URL lines
rest_api_url_lines = st.sampled_from(
    [
        'url = "https://webexapis.com/v1/messages"',
        "fetch('https://webexapis.com/v1/rooms')",
        'base_url = "https://api.ciscospark.com/v1/people"',
        "requests.get('https://webexapis.com/v1/teams')",
    ]
)

# BYOVA pattern lines
byova_pattern_lines = st.sampled_from(
    [
        "service VoiceVirtualAgent {",
        "from byova_common import something",
        "class VoiceVirtualAgent:",
    ]
)

# Safe filler lines that contain NO Webex-related content
safe_filler_lines = st.sampled_from(
    [
        "x = 1 + 2",
        "print('hello world')",
        "def compute(a, b): return a + b",
        "import os",
        "import sys",
        "result = []",
        "for i in range(10): pass",
        "# just a comment",
        "logger.info('processing')",
        "class MyApp: pass",
    ]
)

# Strategy: code block with only safe filler (no Webex content)
non_webex_code = st.lists(safe_filler_lines, min_size=1, max_size=10).map(
    lambda lines: "\n".join(lines)
)

# Strategy: code block that contains at least one SDK import line
code_with_sdk_import = st.tuples(
    st.lists(safe_filler_lines, min_size=0, max_size=5),
    all_sdk_imports,
    st.lists(safe_filler_lines, min_size=0, max_size=5),
).map(lambda t: "\n".join(t[0] + [t[1]] + t[2]))

# Strategy: code block that contains at least one REST API URL
code_with_rest_url = st.tuples(
    st.lists(safe_filler_lines, min_size=0, max_size=5),
    rest_api_url_lines,
    st.lists(safe_filler_lines, min_size=0, max_size=5),
).map(lambda t: "\n".join(t[0] + [t[1]] + t[2]))

# Strategy: code block that contains at least one BYOVA pattern
code_with_byova = st.tuples(
    st.lists(safe_filler_lines, min_size=0, max_size=5),
    byova_pattern_lines,
    st.lists(safe_filler_lines, min_size=0, max_size=5),
).map(lambda t: "\n".join(t[0] + [t[1]] + t[2]))

# Strategy: JSON content with manifest detection keys
manifest_json_content = st.fixed_dictionaries(
    {"area": st.text(min_size=1, max_size=20), "comp": st.text(min_size=1, max_size=20)}
).map(lambda d: json.dumps(d))

# Strategy: JSON filenames
json_filenames = (
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="_-"
        ),
        min_size=1,
        max_size=20,
    )
    .filter(lambda s: s.strip())
    .map(lambda s: f"layouts/{s}.json")
)


# ---------------------------------------------------------------------------
# Property 20: Webex ecosystem signal detection (Tier 1)
# ---------------------------------------------------------------------------
# **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.13, 11.14**


@given(code=code_with_sdk_import)
@settings(max_examples=100)
def test_sdk_import_detection(code: str) -> None:
    """SDK import patterns in code are detected as SDK_IMPORT signals."""
    detector = _make_detector()
    signals = detector.detect_sdk_imports(code, "app.py")
    assert len(signals) >= 1, (
        f"Expected at least one SDK import signal, got {len(signals)}"
    )
    known_sdk_names = {e.name for e in SDK_CATALOG_ENTRIES}
    for sig in signals:
        assert sig.signal_type == SignalType.SDK_IMPORT
        assert sig.file_path == "app.py"
        assert sig.line_number >= 1
        assert sig.matched_value != ""
        assert sig.catalog_entry in known_sdk_names, (
            f"catalog_entry '{sig.catalog_entry}' not in known SDK names"
        )


@given(code=code_with_rest_url)
@settings(max_examples=100)
def test_rest_api_url_detection(code: str) -> None:
    """REST API URL patterns (webexapis.com, api.ciscospark.com) are detected as REST_API_URL signals."""
    detector = _make_detector()
    signals = detector.detect_rest_api_urls(code, "client.py")
    assert len(signals) >= 1, (
        f"Expected at least one REST API URL signal, got {len(signals)}"
    )
    for sig in signals:
        assert sig.signal_type == SignalType.REST_API_URL
        assert sig.file_path == "client.py"
        assert sig.line_number >= 1
        assert (
            "webexapis.com" in sig.matched_value.lower()
            or "api.ciscospark.com" in sig.matched_value.lower()
        )


@given(json_content=manifest_json_content, filename=json_filenames)
@settings(max_examples=100)
def test_widget_manifest_detection(json_content: str, filename: str) -> None:
    """JSON files containing manifest detection keys (area, comp) are detected as WIDGET_MANIFEST signals."""
    # Build a PRFile with the JSON content as the patch (using diff-style + prefix)
    patch_lines = [f"+{line}" for line in json_content.splitlines()]
    patch = "\n".join(patch_lines)
    pr_file = PRFile(
        filename=filename,
        status="added",
        additions=len(patch_lines),
        deletions=0,
        patch=patch,
    )
    detector = _make_detector()
    signals = detector.detect_widget_manifests([pr_file])
    assert len(signals) >= 1, (
        f"Expected at least one widget manifest signal, got {len(signals)}"
    )
    for sig in signals:
        assert sig.signal_type == SignalType.WIDGET_MANIFEST
        assert sig.file_path == filename
        assert sig.technology == "Contact Center"


@given(code=code_with_byova)
@settings(max_examples=100)
def test_byova_pattern_detection(code: str) -> None:
    """BYOVA patterns (e.g., VoiceVirtualAgent) in code are detected as BYOVA_PATTERN signals."""
    detector = _make_detector()
    signals = detector.detect_byova_patterns(code, "service.proto")
    assert len(signals) >= 1, (
        f"Expected at least one BYOVA pattern signal, got {len(signals)}"
    )
    for sig in signals:
        assert sig.signal_type in (SignalType.BYOVA_PATTERN, SignalType.FLOW_REFERENCE)
        assert sig.file_path == "service.proto"
        assert sig.line_number >= 1


@given(code=non_webex_code)
@settings(max_examples=100)
def test_no_signals_for_non_webex_code(code: str) -> None:
    """Code with no Webex-related content produces no ecosystem signals."""
    detector = _make_detector()
    pr_file = PRFile(
        filename="app.py",
        status="modified",
        additions=5,
        deletions=0,
        patch=code,
    )
    signals = detector.detect_signals([pr_file])
    assert signals == [], (
        f"Expected no signals for non-Webex code, got {len(signals)}: {signals}"
    )


@given(
    sdk_import=all_sdk_imports,
    filler=st.lists(safe_filler_lines, min_size=0, max_size=5),
)
@settings(max_examples=100)
def test_sdk_import_only_usage_warning(sdk_import: str, filler: list[str]) -> None:
    """SDK imported but never used beyond the import statement produces a WARNING finding."""
    # Build code that imports the SDK but never references it again
    code = "\n".join([sdk_import] + filler)
    detector = _make_detector()
    sdk_signals = detector.detect_sdk_imports(code, "app.py")
    # Only proceed if we actually detected an import
    if not sdk_signals:
        return
    findings = detector.check_sdk_usage(code, sdk_signals)
    assert len(findings) >= 1, (
        f"Expected at least one warning finding for import-only usage"
    )
    for finding in findings:
        assert finding.severity == Severity.WARNING
        assert finding.rule_id == "ecosystem-sdk-import-only"
        assert finding.file_path == "app.py"


@given(
    sdk_import=python_sdk_imports,
    filler=st.lists(safe_filler_lines, min_size=0, max_size=3),
)
@settings(max_examples=100)
def test_sdk_actually_used_no_warning(sdk_import: str, filler: list[str]) -> None:
    """SDK imported AND used beyond the import statement produces no warning findings."""
    # Derive a usage term from the import to ensure the SDK is "used"
    if "webexteamssdk" in sdk_import:
        if "WebexTeamsAPI" in sdk_import:
            usage_line = "client = WebexTeamsAPI()"
        else:
            usage_line = "api = webexteamssdk.WebexTeamsAPI()"
    elif "wxc_sdk" in sdk_import:
        if "WebexSimpleApi" in sdk_import:
            usage_line = "api = WebexSimpleApi(tokens=token)"
        else:
            usage_line = "api = wxc_sdk.WebexSimpleApi()"
    else:
        usage_line = "webex.init()"

    code = "\n".join([sdk_import] + filler + [usage_line])
    detector = _make_detector()
    sdk_signals = detector.detect_sdk_imports(code, "app.py")
    if not sdk_signals:
        return
    findings = detector.check_sdk_usage(code, sdk_signals)
    assert findings == [], (
        f"Expected no warnings when SDK is used, got {len(findings)}: {findings}"
    )


@given(
    sdk_code=code_with_sdk_import,
    rest_code=code_with_rest_url,
    byova_code=code_with_byova,
    manifest_json=manifest_json_content,
    json_fname=json_filenames,
)
@settings(max_examples=100)
def test_detect_signals_aggregates_all_sub_detectors(
    sdk_code: str,
    rest_code: str,
    byova_code: str,
    manifest_json: str,
    json_fname: str,
) -> None:
    """detect_signals aggregates results from SDK, REST, BYOVA, and manifest sub-detectors."""
    # Build PRFiles with different signal types
    sdk_file = PRFile(
        filename="sdk_app.py",
        status="added",
        additions=5,
        deletions=0,
        patch=sdk_code,
    )
    rest_file = PRFile(
        filename="rest_client.py",
        status="added",
        additions=5,
        deletions=0,
        patch=rest_code,
    )
    byova_file = PRFile(
        filename="service.proto",
        status="added",
        additions=5,
        deletions=0,
        patch=byova_code,
    )
    manifest_patch = "\n".join(f"+{line}" for line in manifest_json.splitlines())
    manifest_file = PRFile(
        filename=json_fname,
        status="added",
        additions=3,
        deletions=0,
        patch=manifest_patch,
    )

    detector = _make_detector()
    signals = detector.detect_signals([sdk_file, rest_file, byova_file, manifest_file])

    # Collect the distinct signal types found
    signal_types_found = {sig.signal_type for sig in signals}

    # We expect at least SDK_IMPORT, REST_API_URL, and one of BYOVA_PATTERN/FLOW_REFERENCE
    assert SignalType.SDK_IMPORT in signal_types_found, (
        f"Expected SDK_IMPORT in aggregated signals, got types: {signal_types_found}"
    )
    assert SignalType.REST_API_URL in signal_types_found, (
        f"Expected REST_API_URL in aggregated signals, got types: {signal_types_found}"
    )
    assert (
        SignalType.BYOVA_PATTERN in signal_types_found
        or SignalType.FLOW_REFERENCE in signal_types_found
    ), (
        f"Expected BYOVA_PATTERN or FLOW_REFERENCE in aggregated signals, got types: {signal_types_found}"
    )
    assert SignalType.WIDGET_MANIFEST in signal_types_found, (
        f"Expected WIDGET_MANIFEST in aggregated signals, got types: {signal_types_found}"
    )

    # Verify signals reference the correct files
    sdk_signals = [s for s in signals if s.signal_type == SignalType.SDK_IMPORT]
    rest_signals = [s for s in signals if s.signal_type == SignalType.REST_API_URL]
    byova_signals = [
        s
        for s in signals
        if s.signal_type in (SignalType.BYOVA_PATTERN, SignalType.FLOW_REFERENCE)
    ]
    manifest_signals = [
        s for s in signals if s.signal_type == SignalType.WIDGET_MANIFEST
    ]

    assert all(s.file_path == "sdk_app.py" for s in sdk_signals)
    assert all(s.file_path == "rest_client.py" for s in rest_signals)
    assert all(s.file_path == "service.proto" for s in byova_signals)
    assert all(s.file_path == json_fname for s in manifest_signals)
