"""ReviewAgent: MVP orchestrator for rule-based PR code review (no AI)."""

import re
import uuid

from src.codeguard_loader import CodeGuardLoader
from src.github_api_client import GitHubAPIClient
from src.models import Finding, PRFile, Rule, Severity
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.structured_logger import StructuredLogger


class ReviewAgent:
    """Orchestrates the full code review pipeline on a GitHub-hosted runner.

    MVP (Phase 1): rule-based pattern matching only, no AI.
    """

    def __init__(
        self,
        github_client: GitHubAPIClient,
        codeguard_loader: CodeGuardLoader,
        prompt_guard: PromptGuard,
        report_generator: ReviewReportGenerator,
        logger: StructuredLogger,
    ):
        self.github_client = github_client
        self.codeguard_loader = codeguard_loader
        self.prompt_guard = prompt_guard
        self.report_generator = report_generator
        self.logger = logger

    def run(self, owner: str, repo: str, pr_number: int, commit_sha: str) -> None:
        """Execute the MVP review pipeline.

        Steps:
        1. Set Check_Status to "pending"
        2. Fetch PR changed files via GitHubAPIClient
        3. Filter files through PromptGuard allowlist
        4. If no code files after filtering, set Check_Status "failure" and return
        5. Load Rule_Set via CodeGuardLoader
        6. Apply enabled rules as pattern matching against PR diffs
        7. Generate ReviewReport via ReviewReportGenerator
        8. Post inline comments and summary via GitHubAPIClient
        9. Update Check_Status to success/failure based on verdict
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

            # 6. Apply enabled rules as pattern matching against PR diffs
            findings = self._apply_rules(code_files, enabled_rules)
            self.logger.log(
                "info",
                f"Pattern matching produced {len(findings)} findings",
                finding_count=len(findings),
            )

            # 7. Generate ReviewReport
            report = self.report_generator.generate(findings, correlation_id)
            self.logger.log(
                "info",
                f"Report verdict: {report.verdict}",
                verdict=report.verdict,
                summary=report.summary,
            )

            # 8. Post inline comments and summary
            comments = GitHubAPIClient.findings_to_comments(report)
            if comments:
                self.github_client.post_review_comments(
                    owner, repo, pr_number, comments
                )
            summary_text = self._format_summary(report)
            self.github_client.post_review_summary(owner, repo, pr_number, summary_text)

            # 9. Update Check_Status based on verdict
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
            # Wrap entire pipeline: set Check_Status "failure" on unhandled exceptions
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

    def _apply_rules(self, files: list[PRFile], rules: list[Rule]) -> list[Finding]:
        """Apply enabled rules as regex pattern matching against PR diffs.

        For each file's patch, each rule's prompt_or_pattern is compiled as a
        regex and matched against the patch content. Each match produces a Finding.
        """
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
