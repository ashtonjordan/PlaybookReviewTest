"""Entry point for the PR Review Agent, invoked by the GitHub Action workflow."""

import os
import sys
import uuid

from src.codeguard_loader import CodeGuardLoader
from src.github_api_client import GitHubAPIClient
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.review_agent import ReviewAgent
from src.structured_logger import StructuredLogger


def main() -> None:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    owner = os.environ.get("PR_OWNER", "")
    repo = os.environ.get("PR_REPO", "")
    commit_sha = os.environ.get("COMMIT_SHA", "")
    codeguard_path = os.environ.get("CODEGUARD_CHECKOUT_PATH", "codeguard")

    if not all([github_token, pr_number, owner, repo, commit_sha]):
        print("Missing required environment variables.", file=sys.stderr)
        sys.exit(1)

    correlation_id = str(uuid.uuid4())
    logger = StructuredLogger(correlation_id=correlation_id)

    github_client = GitHubAPIClient(github_token=github_token)
    codeguard_loader = CodeGuardLoader(checkout_path=codeguard_path, logger=logger)

    # Load allowlist from CodeGuard rules if available, fall back to defaults
    try:
        rule_set = codeguard_loader.load_rule_set()
        allowlist = codeguard_loader.load_file_allowlist(rule_set)
    except FileNotFoundError:
        allowlist = None

    prompt_guard = PromptGuard(file_allowlist=allowlist)
    report_generator = ReviewReportGenerator()

    agent = ReviewAgent(
        github_client=github_client,
        codeguard_loader=codeguard_loader,
        prompt_guard=prompt_guard,
        report_generator=report_generator,
        logger=logger,
    )

    agent.run(owner=owner, repo=repo, pr_number=pr_number, commit_sha=commit_sha)


if __name__ == "__main__":
    main()
