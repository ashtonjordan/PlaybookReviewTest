"""Property-based tests for REST API endpoint validation (Property 22).

# Feature: github-pr-review-agent, Property 22: REST API endpoint validation (Tier 2)
# Validates: Requirements 11.7, 11.8, 11.9, 11.10
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from src.models import (
    EcosystemSignal,
    RESTEndpointEntry,
    Severity,
    SignalType,
    WebexEcosystemCatalog,
)
from src.webex_ecosystem_detector import WebexEcosystemDetector

# ---------------------------------------------------------------------------
# Catalog helpers
# ---------------------------------------------------------------------------

# A fixed set of documented REST endpoints for testing
DOCUMENTED_ENDPOINTS = [
    RESTEndpointEntry(
        path="/v1/messages",
        method="GET",
        technology="Messaging",
        description="List messages",
    ),
    RESTEndpointEntry(
        path="/v1/rooms",
        method="GET",
        technology="Messaging",
        description="List rooms",
    ),
    RESTEndpointEntry(
        path="/v1/people",
        method="GET",
        technology="Admin",
        description="List people",
    ),
    RESTEndpointEntry(
        path="/v1/teams",
        method="POST",
        technology="Messaging",
        description="Create team",
    ),
    RESTEndpointEntry(
        path="/v1/webhooks",
        method="GET",
        technology="Messaging",
        description="List webhooks",
    ),
]

# Paths that are NOT in the catalog
UNDOCUMENTED_PATHS = [
    "/v1/foobar",
    "/v2/messages",
    "/v1/nonexistent",
    "/v1/secret-endpoint",
    "/v3/admin/users",
]


def _make_catalog(
    endpoints: list[RESTEndpointEntry] | None = None,
) -> WebexEcosystemCatalog:
    return WebexEcosystemCatalog(
        sdk_packages=[],
        rest_endpoints=endpoints if endpoints is not None else DOCUMENTED_ENDPOINTS,
        manifest_patterns=[],
        integration_patterns=[],
    )


def _make_detector(
    endpoints: list[RESTEndpointEntry] | None = None,
) -> WebexEcosystemDetector:
    return WebexEcosystemDetector(_make_catalog(endpoints))


def _make_rest_signal(
    url: str,
    file_path: str = "client.py",
    line_number: int = 1,
) -> EcosystemSignal:
    """Create a REST_API_URL EcosystemSignal from a URL string."""
    return EcosystemSignal(
        signal_type=SignalType.REST_API_URL,
        file_path=file_path,
        line_number=line_number,
        matched_value=url,
        technology="Webex REST API",
        catalog_entry="",
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: pick a documented endpoint path
documented_paths = st.sampled_from([ep.path for ep in DOCUMENTED_ENDPOINTS])

# Strategy: pick an undocumented endpoint path
undocumented_paths = st.sampled_from(UNDOCUMENTED_PATHS)

# Strategy: Webex API base URLs
webex_base_urls = st.sampled_from(
    [
        "https://webexapis.com",
        "https://api.ciscospark.com",
    ]
)

# Strategy: a REST signal with a documented path
documented_rest_signal = st.builds(
    lambda base, path, fname, line: _make_rest_signal(
        url=base + path, file_path=fname, line_number=line
    ),
    base=webex_base_urls,
    path=documented_paths,
    fname=st.just("client.py"),
    line=st.integers(min_value=1, max_value=500),
)

# Strategy: a REST signal with an undocumented path
undocumented_rest_signal = st.builds(
    lambda base, path, fname, line: _make_rest_signal(
        url=base + path, file_path=fname, line_number=line
    ),
    base=webex_base_urls,
    path=undocumented_paths,
    fname=st.just("client.py"),
    line=st.integers(min_value=1, max_value=500),
)

# Strategy: case-variant of a documented path (mixed upper/lower)
case_variant_paths = documented_paths.map(
    lambda p: p[:3] + p[3:].upper()  # e.g., "/v1/MESSAGES"
)

case_variant_rest_signal = st.builds(
    lambda base, path, line: _make_rest_signal(
        url=base + path, file_path="client.py", line_number=line
    ),
    base=webex_base_urls,
    path=case_variant_paths,
    line=st.integers(min_value=1, max_value=500),
)

# Strategy: documented path with trailing slash
trailing_slash_rest_signal = st.builds(
    lambda base, path, line: _make_rest_signal(
        url=base + path + "/", file_path="client.py", line_number=line
    ),
    base=webex_base_urls,
    path=documented_paths,
    line=st.integers(min_value=1, max_value=500),
)


# ---------------------------------------------------------------------------
# Property 22: REST API endpoint validation (Tier 2)
# ---------------------------------------------------------------------------
# **Validates: Requirements 11.7, 11.8, 11.9, 11.10**


@given(signal=documented_rest_signal)
@settings(max_examples=100)
def test_documented_endpoints_produce_no_findings(signal: EcosystemSignal) -> None:
    """REST signals with paths that exist in the catalog produce no findings.

    **Validates: Requirements 11.7, 11.8**
    """
    detector = _make_detector()
    findings = detector.validate_rest_endpoints([signal])
    assert findings == [], (
        f"Expected no findings for documented endpoint, got {len(findings)}: "
        f"{[(f.rule_id, f.description) for f in findings]}"
    )


@given(signal=undocumented_rest_signal)
@settings(max_examples=100)
def test_undocumented_endpoints_produce_warning(signal: EcosystemSignal) -> None:
    """REST signals with paths NOT in the catalog produce WARNING findings
    with rule_id="ecosystem-undocumented-rest-endpoint".

    **Validates: Requirements 11.8, 11.9**
    """
    detector = _make_detector()
    findings = detector.validate_rest_endpoints([signal])
    assert len(findings) == 1, (
        f"Expected exactly 1 finding for undocumented endpoint, got {len(findings)}"
    )
    finding = findings[0]
    assert finding.severity == Severity.WARNING
    assert finding.rule_id == "ecosystem-undocumented-rest-endpoint"
    assert finding.category == "api-security"
    assert finding.file_path == signal.file_path
    assert finding.line_start == signal.line_number


@given(signal=case_variant_rest_signal)
@settings(max_examples=100)
def test_path_matching_is_case_insensitive(signal: EcosystemSignal) -> None:
    """Path matching is case-insensitive — a documented path in different case
    should still match and produce no findings.

    **Validates: Requirements 11.8**
    """
    detector = _make_detector()
    findings = detector.validate_rest_endpoints([signal])
    assert findings == [], (
        f"Expected no findings for case-variant of documented endpoint, "
        f"got {len(findings)}: {[(f.rule_id, f.description) for f in findings]}"
    )


@given(signal=trailing_slash_rest_signal)
@settings(max_examples=100)
def test_trailing_slash_normalization(signal: EcosystemSignal) -> None:
    """Documented paths with trailing slashes should still match (trailing slash normalized).

    **Validates: Requirements 11.8**
    """
    detector = _make_detector()
    findings = detector.validate_rest_endpoints([signal])
    assert findings == [], (
        f"Expected no findings for documented endpoint with trailing slash, "
        f"got {len(findings)}: {[(f.rule_id, f.description) for f in findings]}"
    )


@settings(max_examples=100)
@given(data=st.data())
def test_empty_signals_produce_no_findings(data: st.DataObject) -> None:
    """Empty rest_signals list produces no findings.

    **Validates: Requirements 11.7**
    """
    detector = _make_detector()
    findings = detector.validate_rest_endpoints([])
    assert findings == [], (
        f"Expected no findings for empty signal list, got {len(findings)}"
    )


@given(
    documented=st.lists(documented_rest_signal, min_size=1, max_size=3),
    undocumented=st.lists(undocumented_rest_signal, min_size=1, max_size=3),
)
@settings(max_examples=100)
def test_mixed_endpoints_findings_only_for_undocumented(
    documented: list[EcosystemSignal],
    undocumented: list[EcosystemSignal],
) -> None:
    """Mixed documented/undocumented endpoints produce findings only for undocumented ones.

    **Validates: Requirements 11.8, 11.9, 11.10**
    """
    detector = _make_detector()
    all_signals = documented + undocumented
    findings = detector.validate_rest_endpoints(all_signals)

    # Should have exactly as many findings as undocumented signals
    assert len(findings) == len(undocumented), (
        f"Expected {len(undocumented)} findings (one per undocumented endpoint), "
        f"got {len(findings)}"
    )

    # All findings should be warnings for undocumented endpoints
    for finding in findings:
        assert finding.severity == Severity.WARNING
        assert finding.rule_id == "ecosystem-undocumented-rest-endpoint"
        assert finding.category == "api-security"
