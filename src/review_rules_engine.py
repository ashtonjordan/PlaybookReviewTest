"""ReviewRulesEngine: loads, validates, and manages review rules from YAML/JSON Rule_Set files."""

import json
import os
from pathlib import Path

import yaml

from src.models import VALID_CATEGORIES, Rule, RuleSet, Severity


class ValidationError(Exception):
    """Raised when a Rule_Set file or rule fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class ReviewRulesEngine:
    """Loads, validates, and manages review rules from YAML/JSON Rule_Set files."""

    def load(self, file_path: str) -> RuleSet:
        """Parse a YAML or JSON Rule_Set file. Raises ValidationError on invalid input."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Rule_Set file not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        ext = path.suffix.lower()

        if ext in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif ext == ".json":
            data = json.loads(content)
        else:
            raise ValidationError(
                [f"Unsupported file format: {ext}. Use .yaml, .yml, or .json"]
            )

        if not isinstance(data, dict):
            raise ValidationError(
                ["Rule_Set file must contain a mapping/object at the top level"]
            )

        return self._parse_rule_set(data)

    def _parse_rule_set(self, data: dict) -> RuleSet:
        """Parse a dict into a RuleSet, validating all rules."""
        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ValidationError(["'rules' field must be a list"])

        rules: list[Rule] = []
        all_errors: list[str] = []

        for i, raw_rule in enumerate(raw_rules):
            if not isinstance(raw_rule, dict):
                all_errors.append(f"Rule at index {i}: must be a mapping/object")
                continue

            rule, errors = self._parse_rule(raw_rule, i)
            if errors:
                all_errors.extend(errors)
            else:
                assert rule is not None
                rule_errors = self.validate_rule(rule)
                if rule_errors:
                    all_errors.extend(rule_errors)
                else:
                    rules.append(rule)

        if all_errors:
            raise ValidationError(all_errors)

        version = str(data.get("version", "1.0"))
        file_allowlist = data.get("file_allowlist", [])
        if not isinstance(file_allowlist, list):
            file_allowlist = []

        return RuleSet(rules=rules, version=version, file_allowlist=file_allowlist)

    def _parse_rule(self, raw: dict, index: int) -> tuple[Rule | None, list[str]]:
        """Parse a single rule dict into a Rule object. Returns (rule, errors)."""
        errors: list[str] = []
        prefix = f"Rule at index {index}"

        required_fields = [
            "id",
            "category",
            "description",
            "severity",
            "prompt_or_pattern",
        ]
        for field in required_fields:
            if field not in raw or raw[field] is None:
                errors.append(f"{prefix}: missing required field '{field}'")

        if errors:
            return None, errors

        # Parse severity
        severity_str = str(raw["severity"]).lower()
        try:
            severity = Severity(severity_str)
        except ValueError:
            errors.append(
                f"{prefix}: invalid severity '{raw['severity']}'. Must be one of: error, warning, info"
            )
            return None, errors

        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = bool(enabled)

        rule = Rule(
            id=str(raw["id"]),
            category=str(raw["category"]),
            description=str(raw["description"]),
            severity=severity,
            prompt_or_pattern=str(raw["prompt_or_pattern"]),
            enabled=enabled,
            languages=raw.get("languages", [])
            if isinstance(raw.get("languages"), list)
            else [],
            tags=raw.get("tags", []) if isinstance(raw.get("tags"), list) else [],
        )
        return rule, []

    def validate_rule(self, rule: Rule) -> list[str]:
        """Validate a single rule has all required fields and valid values. Returns list of error messages."""
        errors: list[str] = []

        if not rule.id or not rule.id.strip():
            errors.append(f"Rule '{rule.id}': 'id' must be a non-empty string")

        if not rule.category or not rule.category.strip():
            errors.append(f"Rule '{rule.id}': 'category' must be a non-empty string")
        elif rule.category not in VALID_CATEGORIES:
            errors.append(
                f"Rule '{rule.id}': invalid category '{rule.category}'. "
                f"Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        if not rule.description or not rule.description.strip():
            errors.append(f"Rule '{rule.id}': 'description' must be a non-empty string")

        if not isinstance(rule.severity, Severity):
            errors.append(f"Rule '{rule.id}': 'severity' must be a Severity enum value")

        if not rule.prompt_or_pattern or not rule.prompt_or_pattern.strip():
            errors.append(
                f"Rule '{rule.id}': 'prompt_or_pattern' must be a non-empty string"
            )

        return errors

    def filter_by_category(self, rule_set: RuleSet, category: str) -> list[Rule]:
        """Filter rules by Codeguard_Rule_Category."""
        return [r for r in rule_set.rules if r.category == category]

    def get_enabled_rules(self, rule_set: RuleSet) -> list[Rule]:
        """Return only enabled rules."""
        return [r for r in rule_set.rules if r.enabled]

    def print_rule_set(self, rule_set: RuleSet, format: str = "yaml") -> str:
        """Serialize a RuleSet back to YAML or JSON string."""
        data = self._rule_set_to_dict(rule_set)

        if format.lower() == "json":
            return json.dumps(data, indent=2, sort_keys=False)
        elif format.lower() in ("yaml", "yml"):
            return yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'yaml' or 'json'")

    def _rule_set_to_dict(self, rule_set: RuleSet) -> dict:
        """Convert a RuleSet to a plain dict for serialization."""
        return {
            "version": rule_set.version,
            "file_allowlist": rule_set.file_allowlist,
            "rules": [self._rule_to_dict(r) for r in rule_set.rules],
        }

    def _rule_to_dict(self, rule: Rule) -> dict:
        """Convert a Rule to a plain dict for serialization."""
        d = {
            "id": rule.id,
            "category": rule.category,
            "description": rule.description,
            "severity": rule.severity.value,
            "prompt_or_pattern": rule.prompt_or_pattern,
            "enabled": rule.enabled,
        }
        if rule.languages:
            d["languages"] = rule.languages
        if rule.tags:
            d["tags"] = rule.tags
        return d
