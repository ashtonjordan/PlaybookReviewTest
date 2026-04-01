"""ReviewAgent: orchestrator for PR code review (rule-based + AI)."""

import os
import re

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


class ReviewAgent:
    """Orchestrates the full code review pipeline on a GitHub-hosted runner."""

    def __init__(
        self,
        github_client: GitHubAPIClient,
        codeguard_loader: CodeGuardLoader,
        prompt_guard: PromptGuard,
        report_generator: ReviewReportGenerator,
        logger: StructuredLogger,
        ai_client: AIModelClient | None = None,
    ):
        self.github_client = github_client
        self.codeguard_loader = codeguard_loader
        self.prompt_guard = prompt_guard
        self.report_generator = report_generator
        self.logger = logger
        self.ai_client = ai_client

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

            # 7. AI analysis (if client available)
            if self.ai_client is not None:
                ai_findings = self._run_ai_analysis(code_files, enabled_rules)
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

            # 9. Post inline comments and summary
            comments = GitHubAPIClient.findings_to_comments(report)
            if comments:
                self.github_client.post_review_comments(
                    owner, repo, pr_number, comments
                )
            summary_text = self._format_summary(report)
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
                batch_findings = self._parse_ai_findings(response)
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

    def _parse_ai_findings(self, response: dict) -> list[Finding]:
        """Convert validated AI response dict into Finding objects."""
        findings = []
        for item in response.get("findings", []):
            severity_str = item.get("severity", "info").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.INFO

            findings.append(
                Finding(
                    file_path=item.get("file_path", ""),
                    line_start=int(item.get("line_number", 0)),
                    line_end=int(item.get("line_number", 0)),
                    rule_id=item.get("rule_id", "ai-finding"),
                    category=item.get("category", "ai-review"),
                    severity=severity,
                    description=item.get("description", ""),
                )
            )
        return findings

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
    def _format_summary(report) -> str:
        """Format a ReviewReport into a human-readable summary string."""
        lines = [f"## PR Review — {report.verdict.upper()}\n"]
        lines.append(f"**Findings:** {len(report.findings)} total")
        for severity, count in sorted(report.summary.items()):
            if count > 0:
                lines.append(f"- {severity}: {count}")
        if not report.findings:
            lines.append("\nNo issues found. Looks good!")
        return "\n".join(lines)
