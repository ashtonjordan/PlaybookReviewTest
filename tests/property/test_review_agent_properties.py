"""Property tests for ReviewAgent — unrecoverable errors set check status to failure.

Feature: github-pr-review-agent, Property 9: Unrecoverable errors set check status to failure
Validates: Requirements 7.1
"""

from unittest.mock import MagicMock, call, patch

import hypothesis.strategies as st
from hypothesis import given, settings

from src.codeguard_loader import CodeGuardLoader
from src.github_api_client import GitHubAPIClient
from src.models import PRFile
from src.prompt_guard import PromptGuard
from src.report_generator import ReviewReportGenerator
from src.review_agent import ReviewAgent
from src.structured_logger import StructuredLogger


# --- Strategies ---

exception_types = st.sampled_from(
    [
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        IOError,
        FileNotFoundError,
        ConnectionError,
        PermissionError,
    ]
)

error_messages = st.text(min_size=1, max_size=100).filter(lambda s: s.strip())

owner_repo = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

pr_numbers = st.integers(min_value=1, max_value=99999)

commit_shas = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=7,
    max_size=40,
).filter(lambda s: s.strip())


def _make_agent() -> tuple[ReviewAgent, MagicMock, MagicMock]:
    """Create a ReviewAgent with mocked dependencies. Returns (agent, github_client_mock, logger_mock)."""
    github_client = MagicMock(spec=GitHubAPIClient)
    codeguard_loader = MagicMock(spec=CodeGuardLoader)
    prompt_guard = MagicMock(spec=PromptGuard)
    report_generator = MagicMock(spec=ReviewReportGenerator)
    logger = MagicMock(spec=StructuredLogger)
    logger.correlation_id = "test-correlation-id"

    agent = ReviewAgent(
        github_client=github_client,
        codeguard_loader=codeguard_loader,
        prompt_guard=prompt_guard,
        report_generator=report_generator,
        logger=logger,
    )
    return agent, github_client, logger


# --- Property 9: Unrecoverable errors set check status to failure ---


@given(
    exc_type=exception_types,
    msg=error_messages,
    owner=owner_repo,
    repo=owner_repo,
    pr_number=pr_numbers,
    sha=commit_shas,
)
@settings(max_examples=100)
def test_unrecoverable_error_during_fetch_sets_check_failure(
    exc_type, msg, owner, repo, pr_number, sha
):
    """Property 9: When fetch_pr_files raises an unrecoverable exception,
    the agent sets Check_Status to 'failure' and logs the error."""
    agent, github_client, logger = _make_agent()

    # Make fetch_pr_files raise an unrecoverable error
    github_client.fetch_pr_files.side_effect = exc_type(msg)

    try:
        agent.run(owner, repo, pr_number, sha)
    except Exception:
        pass  # Agent re-raises after setting check status

    # Assert check run was called with conclusion="failure"
    failure_calls = [
        c
        for c in github_client.create_check_run.call_args_list
        if c.kwargs.get("conclusion") == "failure"
        or (len(c.args) > 4 and c.args[4] == "failure")
    ]
    assert len(failure_calls) >= 1, (
        "Check_Status should be set to 'failure' on unhandled exception"
    )

    # Assert error was logged
    error_log_calls = [c for c in logger.log.call_args_list if c.args[0] == "error"]
    assert len(error_log_calls) >= 1, "Error should be logged on unhandled exception"


@given(
    exc_type=exception_types,
    msg=error_messages,
    owner=owner_repo,
    repo=owner_repo,
    pr_number=pr_numbers,
    sha=commit_shas,
)
@settings(max_examples=100)
def test_unrecoverable_error_during_rule_loading_sets_check_failure(
    exc_type, msg, owner, repo, pr_number, sha
):
    """Property 9: When codeguard_loader.load_rule_set raises an exception,
    the agent sets Check_Status to 'failure' and logs the error."""
    agent, github_client, logger = _make_agent()

    # fetch_pr_files succeeds, returns some code files
    github_client.fetch_pr_files.return_value = [
        PRFile(
            filename="app.py",
            status="added",
            additions=10,
            deletions=0,
            patch="+print('hello')",
        )
    ]
    # filter_files passes them through
    agent.prompt_guard.filter_files.return_value = [
        PRFile(
            filename="app.py",
            status="added",
            additions=10,
            deletions=0,
            patch="+print('hello')",
        )
    ]
    # load_rule_set raises
    agent.codeguard_loader.load_rule_set.side_effect = exc_type(msg)

    try:
        agent.run(owner, repo, pr_number, sha)
    except Exception:
        pass

    failure_calls = [
        c
        for c in github_client.create_check_run.call_args_list
        if c.kwargs.get("conclusion") == "failure"
        or (len(c.args) > 4 and c.args[4] == "failure")
    ]
    assert len(failure_calls) >= 1, (
        "Check_Status should be set to 'failure' on rule loading error"
    )

    error_log_calls = [c for c in logger.log.call_args_list if c.args[0] == "error"]
    assert len(error_log_calls) >= 1, "Error should be logged on rule loading failure"


@given(
    exc_type=exception_types,
    msg=error_messages,
    owner=owner_repo,
    repo=owner_repo,
    pr_number=pr_numbers,
    sha=commit_shas,
)
@settings(max_examples=100)
def test_unrecoverable_error_during_comment_posting_sets_check_failure(
    exc_type, msg, owner, repo, pr_number, sha
):
    """Property 9: When posting review comments raises an exception,
    the agent sets Check_Status to 'failure' and logs the error."""
    agent, github_client, logger = _make_agent()

    from src.models import Finding, ReviewReport, RuleSet, Rule, Severity

    github_client.fetch_pr_files.return_value = [
        PRFile(
            filename="app.py",
            status="added",
            additions=10,
            deletions=0,
            patch="+print('hello')",
        )
    ]
    agent.prompt_guard.filter_files.return_value = [
        PRFile(
            filename="app.py",
            status="added",
            additions=10,
            deletions=0,
            patch="+print('hello')",
        )
    ]
    agent.codeguard_loader.load_rule_set.return_value = RuleSet(rules=[], version="1.0")

    # report_generator returns a report with findings
    report = ReviewReport(
        verdict="pass",
        findings=[],
        summary={"error": 0, "warning": 0, "info": 0},
        correlation_id="test",
    )
    agent.report_generator.generate.return_value = report

    # post_review_summary raises
    github_client.post_review_summary.side_effect = exc_type(msg)

    try:
        agent.run(owner, repo, pr_number, sha)
    except Exception:
        pass

    failure_calls = [
        c
        for c in github_client.create_check_run.call_args_list
        if c.kwargs.get("conclusion") == "failure"
        or (len(c.args) > 4 and c.args[4] == "failure")
    ]
    assert len(failure_calls) >= 1, (
        "Check_Status should be set to 'failure' on comment posting error"
    )

    error_log_calls = [c for c in logger.log.call_args_list if c.args[0] == "error"]
    assert len(error_log_calls) >= 1, (
        "Error should be logged on comment posting failure"
    )
