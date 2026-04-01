"""GitHubAPIClient: communicates with GitHub REST API using the GITHUB_TOKEN."""

import random
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json

from src.models import PRFile, ReviewComment, ReviewReport


class GitHubAPIError(Exception):
    """Raised when a GitHub API call fails after all retries."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


def _is_retryable(status_code: int) -> bool:
    """Return True if the HTTP status code is transient/retryable."""
    return status_code in (429, 500, 502, 503, 504)


class GitHubAPIClient:
    """Communicates with GitHub REST API using the GITHUB_TOKEN from the workflow."""

    BASE_URL = "https://api.github.com"
    MAX_RETRIES = 3
    BACKOFF_BASE = 1.0
    MAX_DELAY = 30.0

    def __init__(self, github_token: str):
        self.github_token = github_token

    # -- Public API --

    def fetch_pr_files(self, owner: str, repo: str, pr_number: int) -> list[PRFile]:
        """Fetch changed files and diffs. Handles pagination. Retries on transient errors."""
        files: list[PRFile] = []
        page = 1
        per_page = 100  # GitHub max per page for this endpoint

        while True:
            url = (
                f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/files"
                f"?per_page={per_page}&page={page}"
            )
            data = self._request("GET", url)
            if not data:
                break
            files.extend(
                PRFile(
                    filename=f["filename"],
                    status=f.get("status", "modified"),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch", ""),
                )
                for f in data
            )
            if len(data) < per_page:
                break
            page += 1

        return files

    def create_check_run(
        self,
        owner: str,
        repo: str,
        sha: str,
        status: str,
        conclusion: str | None = None,
        output: dict | None = None,
    ) -> None:
        """Create or update a Check Run on a commit."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/check-runs"
        body: dict = {"name": "PR Review Agent", "head_sha": sha, "status": status}
        if conclusion is not None:
            body["conclusion"] = conclusion
        if output is not None:
            body["output"] = output
        self._request("POST", url, body=body)

    def post_review_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comments: list[ReviewComment],
    ) -> None:
        """Post inline review comments on specific file/line locations."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        gh_comments = [
            {"path": c.file_path, "line": c.line, "body": c.body} for c in comments
        ]
        body = {"event": "COMMENT", "comments": gh_comments}
        self._request("POST", url, body=body)

    def post_review_summary(
        self, owner: str, repo: str, pr_number: int, summary: str
    ) -> None:
        """Post a top-level PR review comment with the summary."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        self._request("POST", url, body={"body": summary})

    # -- Verdict / comment helpers --

    @staticmethod
    def verdict_to_conclusion(verdict: str) -> str:
        """Map a ReviewReport verdict to a GitHub Check Run conclusion.

        "pass" → "success", "fail" → "failure".
        """
        return "success" if verdict == "pass" else "failure"

    @staticmethod
    def findings_to_comments(report: ReviewReport) -> list[ReviewComment]:
        """Convert ReviewReport findings into rich ReviewComment objects.

        Only posts inline comments for error and warning severity.
        Info findings are included in the summary only to reduce noise.
        """
        severity_icons = {"error": "🔴", "warning": "🟡", "info": "🔵"}

        comments = []
        for f in report.findings:
            # Skip info-level findings from inline comments — summary only
            if f.severity.value == "info":
                continue

            icon = severity_icons.get(f.severity.value, "⚪")
            lines = [
                f"{icon} **{f.severity.value.upper()}** | Rule: `{f.rule_id}`",
                "",
                f.description,
            ]
            if f.remediation:
                lines.append("")
                lines.append(f"**How to fix:** {f.remediation}")

            comments.append(
                ReviewComment(
                    file_path=f.file_path,
                    line=f.line_start,
                    body="\n".join(lines),
                )
            )
        return comments

    # -- Internal helpers --

    def _request(self, method: str, url: str, body: dict | None = None) -> dict | list:
        """Execute an HTTP request with retry and exponential backoff.

        Retries up to MAX_RETRIES times on transient HTTP errors (429, 5xx).
        Uses exponential backoff with jitter:
            delay = min(BACKOFF_BASE * 2^attempt + random(0,1), MAX_DELAY)
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return self._do_request(method, url, body)
            except HTTPError as exc:
                last_error = exc
                if not _is_retryable(exc.code) or attempt == self.MAX_RETRIES:
                    raise GitHubAPIError(
                        f"GitHub API error: {exc.code} {exc.reason}",
                        status_code=exc.code,
                    ) from exc
                delay = min(
                    self.BACKOFF_BASE * (2**attempt) + random.uniform(0, 1),
                    self.MAX_DELAY,
                )
                time.sleep(delay)
            except OSError as exc:
                last_error = exc
                if attempt == self.MAX_RETRIES:
                    raise GitHubAPIError(f"GitHub API connection error: {exc}") from exc
                delay = min(
                    self.BACKOFF_BASE * (2**attempt) + random.uniform(0, 1),
                    self.MAX_DELAY,
                )
                time.sleep(delay)

        # Should not reach here, but satisfy type checker
        raise GitHubAPIError(f"Request failed after retries: {last_error}")

    def _do_request(
        self, method: str, url: str, body: dict | None = None
    ) -> dict | list:
        """Perform a single HTTP request to the GitHub API."""
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=data, headers=headers, method=method)
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
