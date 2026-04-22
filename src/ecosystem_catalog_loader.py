"""EcosystemCatalogLoader: loads Webex Ecosystem Catalog from the Playbook repo's base branch.

The catalog lives in the Playbook repository at ``.github/rules/`` and is loaded
from the base branch (not the PR branch) to prevent contributors from weakening
validation by modifying the catalog in their PR.

This is separate from CodeGuardLoader because the catalog lives in the Playbook
repo, not in the external CodeGuard repo.
"""

import json
import os
from pathlib import Path

import yaml

from src.models import (
    IntegrationPattern,
    ManifestPattern,
    RESTEndpointEntry,
    SDKPackageEntry,
    WebexEcosystemCatalog,
)
from src.structured_logger import StructuredLogger

# Default catalog filename options (priority order)
_CATALOG_FILENAMES = [
    "ecosystem-catalog.yaml",
    "ecosystem-catalog.yml",
    "ecosystem-catalog.json",
]

# Default path within the repo where the catalog is stored
_RULES_DIR = os.path.join(".github", "rules")


class EcosystemCatalogLoader:
    """Loads Webex_Ecosystem_Catalog from the Playbook repo's base branch."""

    def __init__(self, base_branch_checkout_path: str, logger: StructuredLogger):
        self.base_branch_checkout_path = base_branch_checkout_path
        self.logger = logger

    def load_ecosystem_catalog(self) -> WebexEcosystemCatalog:
        """Load the Webex_Ecosystem_Catalog from .github/rules/ in the base branch checkout.

        Searches for ecosystem-catalog.yaml/.yml/.json in the rules directory.
        Returns a parsed WebexEcosystemCatalog with SDK packages, REST endpoints,
        manifest patterns, and integration patterns.

        Raises:
            FileNotFoundError: If no catalog file is found.
            ValueError: If the catalog file has invalid structure.
        """
        rules_dir = Path(self.base_branch_checkout_path) / _RULES_DIR

        if not rules_dir.is_dir():
            raise FileNotFoundError(
                f"Rules directory not found: {rules_dir}. "
                f"Expected .github/rules/ in the base branch checkout."
            )

        # Find the catalog file
        catalog_path = None
        for filename in _CATALOG_FILENAMES:
            candidate = rules_dir / filename
            if candidate.is_file():
                catalog_path = candidate
                break

        if catalog_path is None:
            raise FileNotFoundError(
                f"No ecosystem catalog found in {rules_dir}. "
                f"Expected one of: {', '.join(_CATALOG_FILENAMES)}"
            )

        self.logger.log(
            "info",
            f"Loading ecosystem catalog from {catalog_path}",
            file=str(catalog_path),
        )

        raw = self._read_catalog_file(catalog_path)
        catalog = self._parse_catalog(raw)

        total = (
            len(catalog.sdk_packages)
            + len(catalog.rest_endpoints)
            + len(catalog.manifest_patterns)
            + len(catalog.integration_patterns)
        )
        self.logger.log(
            "info",
            f"Loaded ecosystem catalog with {total} entries",
            sdk_packages=len(catalog.sdk_packages),
            rest_endpoints=len(catalog.rest_endpoints),
            manifest_patterns=len(catalog.manifest_patterns),
            integration_patterns=len(catalog.integration_patterns),
        )
        return catalog

    def _read_catalog_file(self, path: Path) -> dict:
        """Read and parse a YAML or JSON catalog file."""
        content = path.read_text(encoding="utf-8")

        if path.suffix == ".json":
            data = json.loads(content)
        else:
            data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise ValueError(
                f"Ecosystem catalog must be a YAML/JSON object, got {type(data).__name__}"
            )
        return data

    def _parse_catalog(self, raw: dict) -> WebexEcosystemCatalog:
        """Parse raw catalog dict into a WebexEcosystemCatalog."""
        sdk_packages = [
            self._parse_sdk_entry(entry)
            for entry in raw.get("sdk_packages", [])
            if isinstance(entry, dict)
        ]

        rest_endpoints = [
            self._parse_rest_entry(entry)
            for entry in raw.get("rest_endpoints", [])
            if isinstance(entry, dict)
        ]

        manifest_patterns = [
            self._parse_manifest_entry(entry)
            for entry in raw.get("manifest_patterns", [])
            if isinstance(entry, dict)
        ]

        integration_patterns = [
            self._parse_integration_entry(entry)
            for entry in raw.get("integration_patterns", [])
            if isinstance(entry, dict)
        ]

        return WebexEcosystemCatalog(
            sdk_packages=sdk_packages,
            rest_endpoints=rest_endpoints,
            manifest_patterns=manifest_patterns,
            integration_patterns=integration_patterns,
        )

    def _parse_sdk_entry(self, entry: dict) -> SDKPackageEntry:
        """Parse a single SDK package entry."""
        return SDKPackageEntry(
            name=str(entry.get("name", "")),
            language=str(entry.get("language", "")),
            import_patterns=self._as_str_list(entry.get("import_patterns", [])),
            technology=str(entry.get("technology", "")),
        )

    def _parse_rest_entry(self, entry: dict) -> RESTEndpointEntry:
        """Parse a single REST endpoint entry."""
        return RESTEndpointEntry(
            path=str(entry.get("path", "")),
            method=str(entry.get("method", "")).upper(),
            technology=str(entry.get("technology", "")),
            description=str(entry.get("description", "")),
        )

    def _parse_manifest_entry(self, entry: dict) -> ManifestPattern:
        """Parse a single manifest pattern entry."""
        return ManifestPattern(
            pattern_type=str(entry.get("pattern_type", "")),
            detection_keys=self._as_str_list(entry.get("detection_keys", [])),
            technology=str(entry.get("technology", "")),
            description=str(entry.get("description", "")),
        )

    def _parse_integration_entry(self, entry: dict) -> IntegrationPattern:
        """Parse a single integration pattern entry."""
        return IntegrationPattern(
            pattern_type=str(entry.get("pattern_type", "")),
            detection_patterns=self._as_str_list(entry.get("detection_patterns", [])),
            technology=str(entry.get("technology", "")),
            description=str(entry.get("description", "")),
        )

    @staticmethod
    def _as_str_list(value) -> list[str]:
        """Coerce a value to a list of strings."""
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [value]
        return []
