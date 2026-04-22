"""Unit tests for WebexEcosystemDetector.validate() method."""

from src.models import (
    EcosystemSignal,
    Finding,
    PRFile,
    RESTEndpointEntry,
    SDKPackageEntry,
    Severity,
    SignalType,
    WebexEcosystemCatalog,
)
from src.webex_ecosystem_detector import WebexEcosystemDetector


def _empty_catalog() -> WebexEcosystemCatalog:
    return WebexEcosystemCatalog()


def _catalog_with_sdk() -> WebexEcosystemCatalog:
    return WebexEcosystemCatalog(
        sdk_packages=[
            SDKPackageEntry(
                name="webexteamssdk",
                language="python",
                import_patterns=[
                    r"from\s+webexteamssdk\s+import",
                    r"import\s+webexteamssdk",
                ],
                technology="Messaging",
            )
        ],
    )


def _catalog_with_rest() -> WebexEcosystemCatalog:
    return WebexEcosystemCatalog(
        rest_endpoints=[
            RESTEndpointEntry(
                path="/v1/messages",
                method="GET",
                technology="Messaging",
                description="List messages",
            ),
        ],
    )


def _catalog_with_sdk_and_rest() -> WebexEcosystemCatalog:
    return WebexEcosystemCatalog(
        sdk_packages=[
            SDKPackageEntry(
                name="webexteamssdk",
                language="python",
                import_patterns=[
                    r"from\s+webexteamssdk\s+import",
                    r"import\s+webexteamssdk",
                ],
                technology="Messaging",
            )
        ],
        rest_endpoints=[
            RESTEndpointEntry(
                path="/v1/messages",
                method="GET",
                technology="Messaging",
                description="List messages",
            ),
        ],
    )


class TestValidateNoSignals:
    """Tests for validate() when no ecosystem signals are found."""

    def test_no_files_returns_error(self):
        detector = WebexEcosystemDetector(_empty_catalog())
        findings = detector.validate([])
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "ecosystem-no-webex-integration"
        assert findings[0].category == "api-security"
        assert findings[0].file_path == ""
        assert findings[0].line_start == 0
        assert findings[0].line_end == 0

    def test_no_signals_in_code_returns_error(self):
        detector = WebexEcosystemDetector(_empty_catalog())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=5,
                deletions=0,
                patch="print('hello world')\nx = 1 + 2\n",
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "ecosystem-no-webex-integration"

    def test_developer_webex_com_redirect_returns_error(self):
        """Scaffold with only a redirect to developer.webex.com should fail."""
        detector = WebexEcosystemDetector(_empty_catalog())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=3,
                deletions=0,
                patch='redirect_url = "https://developer.webex.com/docs"\nwebbrowser.open(redirect_url)\n',
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "ecosystem-no-webex-integration"


class TestValidateWithSDKSignals:
    """Tests for validate() when SDK import signals are found."""

    def test_sdk_import_used_returns_no_findings(self):
        detector = WebexEcosystemDetector(_catalog_with_sdk())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=5,
                deletions=0,
                patch="from webexteamssdk import WebexTeamsAPI\napi = WebexTeamsAPI()\napi.messages.list()\n",
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 0

    def test_sdk_import_only_returns_warning(self):
        """SDK imported but never used beyond the import line."""
        detector = WebexEcosystemDetector(_catalog_with_sdk())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=3,
                deletions=0,
                patch="from webexteamssdk import WebexTeamsAPI\nprint('hello')\nx = 42\n",
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].rule_id == "ecosystem-sdk-import-only"
        assert findings[0].file_path == "src/app.py"


class TestValidateWithRESTSignals:
    """Tests for validate() when REST API URL signals are found."""

    def test_documented_rest_endpoint_returns_no_findings(self):
        detector = WebexEcosystemDetector(_catalog_with_rest())
        files = [
            PRFile(
                filename="src/api.py",
                status="added",
                additions=3,
                deletions=0,
                patch='url = "https://webexapis.com/v1/messages"\nresponse = requests.get(url)\n',
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 0

    def test_undocumented_rest_endpoint_returns_warning(self):
        detector = WebexEcosystemDetector(_catalog_with_rest())
        files = [
            PRFile(
                filename="src/api.py",
                status="added",
                additions=3,
                deletions=0,
                patch='url = "https://webexapis.com/v1/unknown-endpoint"\nresponse = requests.get(url)\n',
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARNING
        assert findings[0].rule_id == "ecosystem-undocumented-rest-endpoint"


class TestValidateCombinedSignals:
    """Tests for validate() with both SDK and REST signals."""

    def test_sdk_unused_and_undocumented_rest_returns_both_warnings(self):
        detector = WebexEcosystemDetector(_catalog_with_sdk_and_rest())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=5,
                deletions=0,
                patch=(
                    "from webexteamssdk import WebexTeamsAPI\n"
                    'url = "https://webexapis.com/v1/unknown"\n'
                    "print('placeholder')\n"
                ),
            )
        ]
        findings = detector.validate(files)
        rule_ids = {f.rule_id for f in findings}
        assert "ecosystem-sdk-import-only" in rule_ids
        assert "ecosystem-undocumented-rest-endpoint" in rule_ids
        assert all(f.severity == Severity.WARNING for f in findings)

    def test_sdk_used_and_documented_rest_returns_empty(self):
        detector = WebexEcosystemDetector(_catalog_with_sdk_and_rest())
        files = [
            PRFile(
                filename="src/app.py",
                status="added",
                additions=5,
                deletions=0,
                patch=(
                    "from webexteamssdk import WebexTeamsAPI\n"
                    "api = WebexTeamsAPI()\n"
                    'url = "https://webexapis.com/v1/messages"\n'
                    "response = api.messages.list()\n"
                ),
            )
        ]
        findings = detector.validate(files)
        assert len(findings) == 0

    def test_hardcoded_tokens_with_real_endpoints_passes_tier1(self):
        """Real REST endpoints with hardcoded tokens: Tier 1 passes, tokens handled by CodeGuard."""
        detector = WebexEcosystemDetector(_catalog_with_rest())
        files = [
            PRFile(
                filename="src/api.py",
                status="added",
                additions=5,
                deletions=0,
                patch=(
                    'TOKEN = "FAKE_TOKEN_12345"\n'
                    'url = "https://webexapis.com/v1/messages"\n'
                    'headers = {"Authorization": f"Bearer {TOKEN}"}\n'
                    "response = requests.get(url, headers=headers)\n"
                ),
            )
        ]
        findings = detector.validate(files)
        # Should NOT have an error finding — Tier 1 passes because REST URL is detected
        assert not any(f.rule_id == "ecosystem-no-webex-integration" for f in findings)
