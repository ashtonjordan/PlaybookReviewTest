"""CodeGuardLoader: loads Rule_Set from a checked-out CodeGuard release directory.

The real CodeGuard repo (cosai-oasis/project-codeguard) stores rules as
individual markdown files with YAML frontmatter under ``sources/core/``.

This loader supports two modes:
1. **Markdown mode** (real CodeGuard): parses ``sources/core/*.md`` files,
   extracting frontmatter (description, tags, languages) and the markdown
   body as the rule prompt text.
2. **Legacy YAML/JSON mode**: loads a single ``rules.yaml`` / ``rules.json``
   file (useful for unit tests and custom rule sets).
"""

import os
import re
from pathlib import Path

import yaml

from src.models import (
    CODEGUARD_TAG_TO_CATEGORY,
    Rule,
    RuleSet,
    Severity,
    WebexAPIRegistryData,
)
from src.prompt_guard import PromptGuard
from src.review_rules_engine import ReviewRulesEngine
from src.structured_logger import StructuredLogger

# Regex to split YAML frontmatter from markdown body
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


class CodeGuardLoader:
    """Loads Rule_Set and Webex_API_Registry from a checked-out CodeGuard release."""

    # Legacy structured rule set filenames (priority order)
    _RULE_SET_FILENAMES = [
        "rules.yaml",
        "rules.yml",
        "rules.json",
        "ruleset.yaml",
        "ruleset.yml",
        "ruleset.json",
    ]

    # Where the real CodeGuard repo keeps its source rules
    _SOURCES_CORE_DIR = os.path.join("sources", "core")

    def __init__(self, checkout_path: str, logger: StructuredLogger):
        self.checkout_path = checkout_path
        self.logger = logger
        self._engine = ReviewRulesEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_rule_set(self) -> RuleSet:
        """Load and validate the Rule_Set from the CodeGuard release directory.

        Tries the real CodeGuard markdown layout first (``sources/core/*.md``),
        then falls back to a legacy single-file YAML/JSON rule set.
        """
        checkout = Path(self.checkout_path)
        if not checkout.is_dir():
            raise FileNotFoundError(
                f"CodeGuard checkout path does not exist: {self.checkout_path}"
            )

        # 1. Try real CodeGuard layout: sources/core/*.md
        core_dir = checkout / self._SOURCES_CORE_DIR
        if core_dir.is_dir():
            md_files = sorted(core_dir.glob("*.md"))
            if md_files:
                return self._load_from_markdown_sources(md_files)

        # 2. Fallback: legacy single-file rule set
        for name in self._RULE_SET_FILENAMES:
            candidate = checkout / name
            if candidate.is_file():
                self.logger.log(
                    "info",
                    f"Loading Rule_Set from {candidate}",
                    file=str(candidate),
                )
                rule_set = self._engine.load(str(candidate))
                self.logger.log(
                    "info",
                    f"Loaded {len(rule_set.rules)} rules (version {rule_set.version})",
                    rule_count=len(rule_set.rules),
                    version=rule_set.version,
                )
                return rule_set

        raise FileNotFoundError(
            f"No Rule_Set found in {self.checkout_path}. "
            f"Expected sources/core/*.md or one of: "
            f"{', '.join(self._RULE_SET_FILENAMES)}"
        )

    def load_file_allowlist(self, rule_set: RuleSet | None = None) -> set[str]:
        """Extract configurable File_Allowlist from Rule_Set or return defaults."""
        if rule_set is not None and rule_set.file_allowlist:
            custom = set(rule_set.file_allowlist)
            self.logger.log(
                "info",
                f"Using custom file allowlist ({len(custom)} extensions)",
                allowlist=sorted(custom),
            )
            return custom

        self.logger.log("info", "Using default file allowlist")
        return set(PromptGuard.DEFAULT_ALLOWLIST)

    def load_webex_registry(self) -> WebexAPIRegistryData:
        """Load the Webex_API_Registry from the CodeGuard release directory.

        Stub for Phase 3.
        """
        raise NotImplementedError("Phase 3: Webex API registry loading")

    # ------------------------------------------------------------------
    # Markdown source parsing (real CodeGuard layout)
    # ------------------------------------------------------------------

    def _load_from_markdown_sources(self, md_files: list[Path]) -> RuleSet:
        """Parse all markdown rule files from ``sources/core/``."""
        self.logger.log(
            "info",
            f"Loading rules from {len(md_files)} CodeGuard source files",
            source_dir=self._SOURCES_CORE_DIR,
            file_count=len(md_files),
        )

        rules: list[Rule] = []
        for md_path in md_files:
            rule = self._parse_markdown_rule(md_path)
            if rule is not None:
                rules.append(rule)

        self.logger.log(
            "info",
            f"Loaded {len(rules)} rules from CodeGuard sources",
            rule_count=len(rules),
        )
        return RuleSet(rules=rules, version="codeguard")

    def _parse_markdown_rule(self, path: Path) -> Rule | None:
        """Parse a single CodeGuard markdown rule file.

        Expected format::

            ---
            description: Brief description of the rule
            languages:
            - python
            - javascript
            tags:
            - data-security
            alwaysApply: false
            ---

            ## Rule Title
            Markdown body with guidance...
        """
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            self.logger.log(
                "warning",
                f"Failed to read {path.name}: {exc}",
                file=str(path),
            )
            return None

        match = _FRONTMATTER_RE.match(content)
        if not match:
            self.logger.log(
                "warning",
                f"No YAML frontmatter found in {path.name}, skipping",
                file=str(path),
            )
            return None

        raw_frontmatter, body = match.group(1), match.group(2).strip()

        try:
            frontmatter = yaml.safe_load(raw_frontmatter)
        except yaml.YAMLError as exc:
            self.logger.log(
                "warning",
                f"Invalid YAML frontmatter in {path.name}: {exc}",
                file=str(path),
            )
            return None

        if not isinstance(frontmatter, dict):
            return None

        # Derive rule ID from filename: codeguard-0-logging.md -> codeguard-0-logging
        rule_id = path.stem

        description = frontmatter.get("description", rule_id)
        tags = frontmatter.get("tags", [])
        if not isinstance(tags, list):
            tags = [str(tags)]
        languages = frontmatter.get("languages", [])
        if not isinstance(languages, list):
            languages = [str(languages)]

        # Map first recognized tag to a category, default to "general"
        category = "general"
        for tag in tags:
            mapped = CODEGUARD_TAG_TO_CATEGORY.get(tag)
            if mapped:
                category = mapped
                break

        # If no tag matched, try to infer category from the filename
        if category == "general":
            category = self._infer_category_from_filename(rule_id)

        # CodeGuard rules are guidance for AI prompts, not regex patterns.
        # Default severity is WARNING; the AI will decide actual severity per finding.
        return Rule(
            id=rule_id,
            category=category,
            description=description,
            severity=Severity.WARNING,
            prompt_or_pattern=body,
            enabled=True,
            languages=languages,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Category inference from filename
    # ------------------------------------------------------------------

    # Maps filename substrings to categories for rules that lack tags
    _FILENAME_CATEGORY_MAP: dict[str, str] = {
        "cryptography": "data-security",
        "crypto": "data-security",
        "credential": "hardcoded-credentials",
        "hardcoded": "hardcoded-credentials",
        "certificate": "secrets",
        "api-web": "api-security",
        "authentication": "authentication",
        "authorization": "authorization",
        "input-validation": "input-validation",
        "injection": "input-validation",
        "logging": "logging",
        "supply-chain": "supply-chain",
        "framework": "framework-security",
        "data-storage": "data-storage",
        "storage": "data-storage",
        "privacy": "privacy",
        "devops": "devops-containers",
        "container": "devops-containers",
        "kubernetes": "devops-containers",
        "iac": "iac",
        "mobile": "mobile",
        "mcp": "mcp",
        "session": "authentication",
        "cookie": "authentication",
        "xml": "input-validation",
        "serialization": "input-validation",
        "file-handling": "input-validation",
        "upload": "input-validation",
        "client-side": "web",
        "safe-c": "framework-security",
    }

    @classmethod
    def _infer_category_from_filename(cls, rule_id: str) -> str:
        """Best-effort category inference from the rule filename/id."""
        lower = rule_id.lower()
        for substring, category in cls._FILENAME_CATEGORY_MAP.items():
            if substring in lower:
                return category
        return "general"
