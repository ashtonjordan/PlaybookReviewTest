"""ReviewAgent: orchestrator for PR code review (rule-based + AI)."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from src.ai_model_client import (
    AIModelClient,
    BedrockGuardrailError,
    BedrockParseError,
    BedrockThrottlingError,
)
from src.codeguard_loader import CodeGuardLoader
from src.github_api_client import GitHubAPIClient
from src.models import FileDiff, Finding, PRFile, Rule, Severity
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.structured_logger import StructuredLogger

if TYPE_CHECKING:
    from src.ecosystem_catalog_loader import EcosystemCatalogLoader
    from src.scaffold_checker import ScaffoldChecker
    from src.webex_ecosystem_detector import WebexEcosystemDetector


class ReviewAgent:
    """Orchestrates the full code review pipeline on a GitHub-hosted runner."""

    # Directories containing the Agent's own infrastructure code.
    # Files under these paths are excluded from AI analysis and scaffold checks
    # since they are not Playbook scaffolds.
    _AGENT_SOURCE_PREFIXES: tuple[str, ...] = (
        "src/",
        "tests/",
        "scripts/",
        ".github/",
        "docs/",
    )

    def __init__(
        self,
        github_client: GitHubAPIClient,
        codeguard_loader: CodeGuardLoader,
        prompt_guard: PromptGuard,
        report_generator: ReviewReportGenerator,
        logger: StructuredLogger,
        ai_client: AIModelClient | None = None,
        ecosystem_detector: WebexEcosystemDetector | None = None,
        scaffold_checker: ScaffoldChecker | None = None,
        ecosystem_catalog_loader: EcosystemCatalogLoader | None = None,
    ):
        self.github_client = github_client
        self.codeguard_loader = codeguard_loader
        self.prompt_guard = prompt_guard
        self.report_generator = report_generator
        self.logger = logger
        self.ai_client = ai_client
        self.ecosystem_detector = ecosystem_detector
        self.scaffold_checker = scaffold_checker
        self.ecosystem_catalog_loader = ecosystem_catalog_loader

    def run(self, owner: str, repo: str, pr_number: int, commit_sha: str) -> None:
        """Execute the review pipeline.

        Steps:
        1. Set Check_Status to "pending"
        2. Fetch PR changed files via GitHubAPIClient
        3. Filter files through PromptGuard allowlist
        4. If no code files after filtering, set Check_Status "failure" and return
        5. Load Rule_Set via CodeGuardLoader
        6. Apply enabled rules as pattern matching against PR diffs
        7. If AI client available: invoke Bedrock AI analysis
        8. Merge all findings into ReviewReport
        9. Post inline comments and summary via GitHubAPIClient
        10. Update Check_Status to success/failure based on verdict
        """
        correlation_id = self.logger.correlation_id

        try:
            # 1. Set Check_Status to "pending"
            self.logger.log(
                "info",
                "Starting PR review",
                owner=owner,
                repo=repo,
                pr_number=pr_number,
            )
            self.github_client.create_check_run(
                owner, repo, commit_sha, status="in_progress"
            )

            # 2. Fetch PR changed files
            self.logger.log("info", "Fetching PR changed files")
            pr_files = self.github_client.fetch_pr_files(owner, repo, pr_number)
            self.logger.log(
                "info",
                f"Fetched {len(pr_files)} changed files",
                file_count=len(pr_files),
            )

            # 3. Filter files through allowlist
            code_files = self.prompt_guard.filter_files(pr_files)
            self.logger.log(
                "info",
                f"{len(code_files)} code files after filtering",
                code_file_count=len(code_files),
            )

            # 3b. Separate scaffold files from Agent infrastructure files
            scaffold_files = self._filter_scaffold_files(code_files)
            self.logger.log(
                "info",
                f"{len(scaffold_files)} scaffold files (excluded {len(code_files) - len(scaffold_files)} agent source files)",
                scaffold_file_count=len(scaffold_files),
            )

            # 4. If no code files, fail early
            if not code_files:
                self.logger.log(
                    "warning", "No reviewable code files found after filtering"
                )
                self.github_client.create_check_run(
                    owner,
                    repo,
                    commit_sha,
                    status="completed",
                    conclusion="failure",
                    output={
                        "title": "PR Review Agent",
                        "summary": "no reviewable code found",
                    },
                )
                return

            # 5. Load Rule_Set
            self.logger.log("info", "Loading Rule_Set from CodeGuard")
            rule_set = self.codeguard_loader.load_rule_set()
            enabled_rules = [r for r in rule_set.rules if r.enabled]
            self.logger.log(
                "info",
                f"Loaded {len(enabled_rules)} enabled rules",
                rule_count=len(enabled_rules),
            )

            # 6. Apply enabled rules as pattern matching
            findings = self._apply_rules(code_files, enabled_rules)
            self.logger.log(
                "info",
                f"Pattern matching produced {len(findings)} findings",
                finding_count=len(findings),
            )

            # 6b. Ecosystem validation and scaffold checks (optional)
            ecosystem_findings = self._run_ecosystem_and_scaffold_checks(
                scaffold_files, all_files=pr_files
            )
            findings.extend(ecosystem_findings)

            # 7. AI analysis (if client available)
            if self.ai_client is not None:
                ai_findings = self._run_ai_analysis(scaffold_files, enabled_rules)
                findings.extend(ai_findings)
                self.logger.log(
                    "info",
                    f"AI analysis produced {len(ai_findings)} findings",
                    ai_finding_count=len(ai_findings),
                )

            # 8. Generate ReviewReport
            report = self.report_generator.generate(findings, correlation_id)
            self.logger.log(
                "info",
                f"Report verdict: {report.verdict}",
                verdict=report.verdict,
                summary=report.summary,
            )

            # Build audit context for the summary
            audit_context = {
                "total_files": len(pr_files),
                "code_files": len(code_files),
                "scaffold_files": len(scaffold_files),
                "scaffold_filenames": [f.filename for f in scaffold_files],
                "rules_applied": len(enabled_rules),
                "ai_enabled": self.ai_client is not None,
                "ecosystem_enabled": self.ecosystem_catalog_loader is not None
                or self.ecosystem_detector is not None,
            }

            # 9. Post summary (no inline comments — summary contains all findings)
            summary_text = self._format_summary(report, audit_context=audit_context)
            self.github_client.post_review_summary(owner, repo, pr_number, summary_text)

            # 10. Update Check_Status based on verdict
            conclusion = GitHubAPIClient.verdict_to_conclusion(report.verdict)
            self.github_client.create_check_run(
                owner,
                repo,
                commit_sha,
                status="completed",
                conclusion=conclusion,
                output={"title": "PR Review Agent", "summary": summary_text},
            )
            self.logger.log("info", "Review complete", conclusion=conclusion)

        except Exception as exc:
            self.logger.log(
                "error", f"Unhandled exception during review: {exc}", error=str(exc)
            )
            try:
                self.github_client.create_check_run(
                    owner,
                    repo,
                    commit_sha,
                    status="completed",
                    conclusion="failure",
                    output={
                        "title": "PR Review Agent",
                        "summary": f"Review failed: {exc}",
                    },
                )
            except Exception as inner:
                self.logger.log(
                    "error", f"Failed to update check status after error: {inner}"
                )
            raise

    # ------------------------------------------------------------------
    # Ecosystem validation and scaffold checks
    # ------------------------------------------------------------------

    def _run_ecosystem_and_scaffold_checks(
        self, code_files: list[PRFile], all_files: list[PRFile] | None = None
    ) -> list[Finding]:
        """Run Webex ecosystem validation and scaffold structural checks.

        These checks run independently of AI analysis and are only executed
        when the corresponding optional dependencies are configured.

        Args:
            code_files: Files filtered through the allowlist (for code analysis).
            all_files: All PR files before filtering (for manifest/entry point checks).
                       Falls back to code_files if not provided.
        """
        findings: list[Finding] = []
        check_files = all_files if all_files is not None else code_files

        # --- Ecosystem validation ---
        detector = self.ecosystem_detector
        if detector is None and self.ecosystem_catalog_loader is not None:
            # Dynamically load the catalog and create a detector
            try:
                from src.webex_ecosystem_detector import WebexEcosystemDetector

                self.logger.log(
                    "info", "Loading Webex Ecosystem Catalog from base branch"
                )
                catalog = self.ecosystem_catalog_loader.load_ecosystem_catalog()
                detector = WebexEcosystemDetector(catalog)
            except Exception as exc:
                self.logger.log(
                    "warning",
                    f"Failed to load ecosystem catalog: {exc}",
                    error=str(exc),
                )

        if detector is not None:
            try:
                self.logger.log("info", "Running Webex ecosystem validation")
                eco_findings = detector.validate(code_files)
                findings.extend(eco_findings)
                self.logger.log(
                    "info",
                    f"Ecosystem validation produced {len(eco_findings)} findings",
                    ecosystem_finding_count=len(eco_findings),
                )
            except Exception as exc:
                self.logger.log(
                    "warning",
                    f"Ecosystem validation failed, continuing: {exc}",
                    error=str(exc),
                )

        # --- Scaffold structural checks ---
        checker = self.scaffold_checker
        if checker is None:
            # Create a default ScaffoldChecker if not injected
            try:
                from src.scaffold_checker import ScaffoldChecker

                checker = ScaffoldChecker()
            except Exception:
                pass

        if checker is not None:
            try:
                self.logger.log("info", "Running scaffold structural checks")
                scaffold_findings: list[Finding] = []

                entry_point = checker.check_entry_point(check_files)
                if entry_point is not None:
                    scaffold_findings.append(entry_point)

                dep_manifest = checker.check_dependency_manifest(check_files)
                if dep_manifest is not None:
                    scaffold_findings.append(dep_manifest)

                scaffold_findings.extend(checker.check_config_references(code_files))
                scaffold_findings.extend(checker.check_syntax(code_files))

                findings.extend(scaffold_findings)
                self.logger.log(
                    "info",
                    f"Scaffold checks produced {len(scaffold_findings)} findings",
                    scaffold_finding_count=len(scaffold_findings),
                )
            except Exception as exc:
                self.logger.log(
                    "warning",
                    f"Scaffold checks failed, continuing: {exc}",
                    error=str(exc),
                )

        return findings

    # ------------------------------------------------------------------
    # AI analysis
    # ------------------------------------------------------------------

    def _run_ai_analysis(
        self, code_files: list[PRFile], rules: list[Rule]
    ) -> list[Finding]:
        """Run AI-powered analysis on code files using Bedrock."""
        assert self.ai_client is not None

        diffs = [
            FileDiff(
                filename=f.filename,
                patch=f.patch,
                language=self._detect_language(f.filename),
            )
            for f in code_files
            if f.patch
        ]

        if not diffs:
            return []

        system_message = self.prompt_guard.build_system_message()
        all_findings: list[Finding] = []

        # Batch files (≤20 per batch) for large PRs
        batches = AIModelClient.batch_files(diffs)
        self.logger.log(
            "info", f"Processing {len(batches)} AI batch(es)", batch_count=len(batches)
        )

        for batch_idx, batch in enumerate(batches):
            try:
                prompt = self.ai_client.build_prompt(batch, rules)
                response = self.ai_client.analyze(system_message, prompt)

                # Validate response schema
                if not self.prompt_guard.validate_response_schema(response):
                    self.logger.log(
                        "warning",
                        f"AI response for batch {batch_idx} failed schema validation, skipping",
                    )
                    continue

                # Parse findings from validated response
                batch_findings = self._parse_ai_findings(
                    response, code_files=code_files
                )
                all_findings.extend(batch_findings)

            except BedrockGuardrailError as exc:
                self.logger.log(
                    "error",
                    f"Bedrock Guardrails blocked batch {batch_idx}: {exc}",
                    action=exc.action,
                )
                # Guardrail intervention is fatal — report and stop
                raise

            except BedrockThrottlingError as exc:
                self.logger.log(
                    "error",
                    f"Bedrock throttled on batch {batch_idx} after retries: {exc}",
                )
                raise

            except BedrockParseError as exc:
                self.logger.log(
                    "warning",
                    f"AI response for batch {batch_idx} unparseable after retries: {exc}",
                )
                # Continue with other batches

        return all_findings

    def _parse_ai_findings(
        self, response: dict, code_files: list[PRFile] | None = None
    ) -> list[Finding]:
        """Convert validated AI response dict into Finding objects.

        Applies post-processing filters to discard likely hallucinated findings:
        - Findings with no file path
        - Findings referencing file paths not in the PR
        - Findings describing code patterns (SQL, eval, subprocess, etc.)
          that do not actually exist anywhere in the file's diff content
        """
        # Build a set of valid file paths and a map of file content for validation
        valid_files: set[str] = set()
        file_content: dict[str, str] = {}
        if code_files:
            for f in code_files:
                valid_files.add(f.filename)
                file_content[f.filename] = (f.patch or "").lower()

        findings = []
        for item in response.get("findings", []):
            severity_str = item.get("severity", "info").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.INFO

            description = item.get("description", "")
            remediation = item.get("remediation", "")
            rule_id = item.get("rule_id", "ai-finding")
            file_path = item.get("file_path", "")
            line_number = int(item.get("line_number", 0))

            # Filter: discard findings with no file path
            if not file_path:
                continue

            # Filter: discard findings referencing files not in the PR
            if valid_files and file_path not in valid_files:
                continue

            # Filter: discard hallucinated findings where the description
            # mentions specific vulnerability patterns that don't exist
            # anywhere in the actual file content
            if file_path in file_content:
                content = file_content[file_path]
                desc_lower = description.lower()

                # Map of vulnerability claims to code patterns that MUST exist
                # in the file for the claim to be valid
                claim_evidence = {
                    "sql injection": ["cursor.execute", "execute(", ".query(", "sql"],
                    "cursor.execute": ["cursor.execute"],
                    "request.args": ["request.args"],
                    "request.form": ["request.form"],
                    "eval(": ["eval("],
                    "exec(": ["exec("],
                    "subprocess": ["subprocess"],
                    "os.system": ["os.system"],
                    "pickle.loads": ["pickle.loads"],
                    "yaml.load": ["yaml.load"],
                    "innerHTML": ["innerhtml"],
                    "document.write": ["document.write"],
                }

                hallucinated = False
                for claim, evidence_patterns in claim_evidence.items():
                    if claim in desc_lower:
                        # The AI claims this vulnerability exists — verify
                        if not any(pat in content for pat in evidence_patterns):
                            self.logger.log(
                                "info",
                                f"Discarding hallucinated AI finding at {file_path}:{line_number} — "
                                f"description claims '{claim}' but pattern not found in file",
                                rule_id=rule_id,
                            )
                            hallucinated = True
                            break

                if hallucinated:
                    continue

            findings.append(
                Finding(
                    file_path=file_path,
                    line_start=line_number,
                    line_end=line_number,
                    rule_id=rule_id,
                    category=item.get("category", "ai-review"),
                    severity=severity,
                    description=description,
                    remediation=remediation,
                )
            )
        return findings

    @classmethod
    def _filter_scaffold_files(cls, files: list[PRFile]) -> list[PRFile]:
        """Exclude the Agent's own source files, keeping only Playbook scaffold files.

        Files under src/, tests/, scripts/, .github/, docs/ are the Agent's
        infrastructure and should not be reviewed as Playbook scaffolds.
        """
        return [
            f
            for f in files
            if not any(
                f.filename.startswith(prefix) for prefix in cls._AGENT_SOURCE_PREFIXES
            )
        ]

    @staticmethod
    def _detect_language(filename: str) -> str | None:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".go": "go",
            ".rb": "ruby",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".kt": "kotlin",
            ".swift": "swift",
            ".sh": "bash",
        }
        _, ext = os.path.splitext(filename)
        return ext_map.get(ext)

    # ------------------------------------------------------------------
    # Rule-based pattern matching (Phase 1)
    # ------------------------------------------------------------------

    def _apply_rules(self, files: list[PRFile], rules: list[Rule]) -> list[Finding]:
        """Apply enabled rules as regex pattern matching against PR diffs."""
        findings: list[Finding] = []
        for pr_file in files:
            if not pr_file.patch:
                continue
            for rule in rules:
                try:
                    pattern = re.compile(rule.prompt_or_pattern)
                except re.error:
                    continue
                for match in pattern.finditer(pr_file.patch):
                    line_number = pr_file.patch[: match.start()].count("\n") + 1
                    findings.append(
                        Finding(
                            file_path=pr_file.filename,
                            line_start=line_number,
                            line_end=line_number,
                            rule_id=rule.id,
                            category=rule.category,
                            severity=rule.severity,
                            description=f"{rule.description} (matched: {match.group()[:80]})",
                        )
                    )
        return findings

    @staticmethod
    def _format_summary(report, audit_context: dict | None = None) -> str:
        """Format a ReviewReport into a rich, actionable summary string.

        When audit_context is provided, includes details about what was
        checked (files scanned, rules applied, ecosystem signals, etc.)
        for auditability — especially important for clean passes.
        """
        verdict_icon = "✅" if report.verdict == "pass" else "❌"
        lines = [f"## {verdict_icon} PR Review — {report.verdict.upper()}\n"]

        # Only count actionable findings (error + warning)
        actionable = [f for f in report.findings if f.severity.value != "info"]
        error_count = report.summary.get("error", 0)
        warning_count = report.summary.get("warning", 0)

        lines.append(
            f"**{len(actionable)} actionable finding(s)** | "
            f"🔴 {error_count} error(s) | 🟡 {warning_count} warning(s)\n"
        )

        if error_count > 0:
            lines.append(
                "⚠️ **This PR has errors that must be resolved before merging.**\n"
            )

        if actionable:
            lines.append("### Findings\n")
            lines.append("| # | Severity | Rule | File | Line | Description |")
            lines.append("|---|----------|------|------|------|-------------|")

            severity_icons = {"error": "🔴", "warning": "🟡"}
            for i, f in enumerate(actionable, 1):
                icon = severity_icons.get(f.severity.value, "⚪")
                desc_short = f.description[:100]
                if len(f.description) > 100:
                    desc_short += "..."
                lines.append(
                    f"| {i} | {icon} {f.severity.value} | `{f.rule_id}` | "
                    f"`{f.file_path}` | {f.line_start} | {desc_short} |"
                )

            has_remediation = any(f.remediation for f in actionable)
            if has_remediation:
                lines.append("\n### How to Fix\n")
                for i, f in enumerate(actionable, 1):
                    if f.remediation:
                        lines.append(
                            f"**{i}.** `{f.rule_id}` in `{f.file_path}:{f.line_start}`"
                        )
                        lines.append(f"   {f.remediation}\n")
        else:
            lines.append("\n✨ No issues found. Looks good!")

        # Audit trail — always included for transparency
        if audit_context:
            lines.append("\n---\n")
            lines.append("<details><summary>📋 Review Audit Trail</summary>\n")

            total = audit_context.get("total_files", 0)
            code = audit_context.get("code_files", 0)
            scaffold = audit_context.get("scaffold_files", 0)
            rules = audit_context.get("rules_applied", 0)
            ai = audit_context.get("ai_enabled", False)
            eco = audit_context.get("ecosystem_enabled", False)

            lines.append("| Check | Result |")
            lines.append("|---|---|")
            lines.append(
                f"| Files in PR | {total} total, {code} code, {scaffold} scaffold |"
            )
            lines.append(f"| CodeGuard rules applied | {rules} |")
            lines.append(
                f"| AI analysis (Bedrock) | {'✅ Enabled' if ai else '⬜ Disabled'} |"
            )
            lines.append(
                f"| Webex ecosystem validation | {'✅ Enabled' if eco else '⬜ Disabled'} |"
            )
            lines.append(f"| Scaffold structural checks | ✅ Enabled |")

            filenames = audit_context.get("scaffold_filenames", [])
            if filenames:
                lines.append(f"\n**Scaffold files reviewed ({len(filenames)}):**\n")
                for fname in filenames[:30]:  # Cap at 30 to avoid huge summaries
                    lines.append(f"- `{fname}`")
                if len(filenames) > 30:
                    lines.append(f"- ... and {len(filenames) - 30} more")

            lines.append("\n</details>")

        return "\n".join(lines)
