"""Entry point for the PR Review Agent, invoked by the GitHub Action workflow."""

import os
import sys
import uuid

from src.codeguard_loader import CodeGuardLoader
from src.ecosystem_catalog_loader import EcosystemCatalogLoader
from src.github_api_client import GitHubAPIClient
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.review_agent import ReviewAgent
from src.structured_logger import StructuredLogger


def _create_ai_client(logger: StructuredLogger):
    """Create AIModelClient if AWS credentials and model config are available."""
    model_id = os.environ.get("BEDROCK_MODEL_ID", "")
    if not model_id:
        logger.log("info", "BEDROCK_MODEL_ID not set, running in rule-based mode only")
        return None

    try:
        import boto3
    except ImportError:
        logger.log("warning", "boto3 not installed, skipping AI analysis")
        return None

    from src.ai_model_client import AIModelClient

    # boto3 will pick up credentials from the environment
    # (set by aws-actions/configure-aws-credentials)
    session = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-east-1"))

    # Verify credentials are available before proceeding
    credentials = session.get_credentials()
    if credentials is None:
        logger.log("warning", "No AWS credentials found, skipping AI analysis")
        return None

    guardrail_id = os.environ.get("BEDROCK_GUARDRAIL_ID") or None
    guardrail_version = os.environ.get("BEDROCK_GUARDRAIL_VERSION") or None

    logger.log(
        "info",
        "AI analysis enabled",
        model_id=model_id,
        guardrail_id=guardrail_id or "none",
    )

    return AIModelClient(
        boto3_session=session,
        model_id=model_id,
        guardrail_id=guardrail_id,
        guardrail_version=guardrail_version,
    )


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
    ai_client = _create_ai_client(logger)

    # Create ecosystem catalog loader if base branch checkout path is available
    base_branch_path = os.environ.get("BASE_BRANCH_CHECKOUT_PATH", "")
    ecosystem_catalog_loader = None
    if base_branch_path:
        ecosystem_catalog_loader = EcosystemCatalogLoader(
            base_branch_checkout_path=base_branch_path, logger=logger
        )

    agent = ReviewAgent(
        github_client=github_client,
        codeguard_loader=codeguard_loader,
        prompt_guard=prompt_guard,
        report_generator=report_generator,
        logger=logger,
        ai_client=ai_client,
        ecosystem_catalog_loader=ecosystem_catalog_loader,
    )

    agent.run(owner=owner, repo=repo, pr_number=pr_number, commit_sha=commit_sha)


if __name__ == "__main__":
    main()
