"""AIModelClient: invokes Amazon Bedrock Claude model via the Converse API."""

import json
import random
import time

from src.models import FileDiff, Rule, WebexAPIRegistryData


class BedrockThrottlingError(Exception):
    """Raised when Bedrock returns a throttling error."""


class BedrockGuardrailError(Exception):
    """Raised when Bedrock Guardrails block the request or response."""

    def __init__(self, message: str, action: str = ""):
        self.action = action
        super().__init__(message)


class BedrockParseError(Exception):
    """Raised when the AI response cannot be parsed."""


class AIModelClient:
    """Invokes Amazon Bedrock Claude model via the Converse API with Guardrails."""

    THROTTLE_MAX_RETRIES = 3
    THROTTLE_BACKOFF_BASE = 2.0
    THROTTLE_MAX_DELAY = 60.0

    PARSE_MAX_RETRIES = 2

    def __init__(
        self,
        boto3_session,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
    ):
        from botocore.config import Config

        self._client = boto3_session.client(
            "bedrock-runtime",
            region_name="us-east-1",
            config=Config(
                connect_timeout=10,
                read_timeout=120,
                retries={"max_attempts": 0},  # We handle retries ourselves
            ),
        )
        self.model_id = model_id
        self.guardrail_id = guardrail_id
        self.guardrail_version = guardrail_version

    def analyze(self, system_message: str, prompt: str) -> dict:
        """Send a prompt to Bedrock Converse API with optional Guardrails.

        Retries up to 2 times on unparseable responses, 3 times on throttling.
        Returns parsed JSON response dict.
        """
        for parse_attempt in range(self.PARSE_MAX_RETRIES + 1):
            raw_text = self._invoke_with_throttle_retry(system_message, prompt)

            try:
                result = json.loads(raw_text)
                if isinstance(result, dict):
                    return result
                raise BedrockParseError("Response is not a JSON object")
            except (json.JSONDecodeError, BedrockParseError) as exc:
                if parse_attempt == self.PARSE_MAX_RETRIES:
                    raise BedrockParseError(
                        f"Failed to parse AI response after {self.PARSE_MAX_RETRIES + 1} attempts: {exc}"
                    ) from exc
                # Retry with a hint appended to the prompt
                prompt = prompt + (
                    "\n\nIMPORTANT: Your previous response was not valid JSON. "
                    "You MUST respond with ONLY a JSON object. No markdown, no explanation."
                )

        raise BedrockParseError("Exhausted parse retries")

    def _invoke_with_throttle_retry(self, system_message: str, prompt: str) -> str:
        """Call Bedrock Converse API with throttle retry logic. Returns raw text."""
        for attempt in range(self.THROTTLE_MAX_RETRIES + 1):
            try:
                return self._call_converse(system_message, prompt)
            except self._client.exceptions.ThrottlingException as exc:
                if attempt == self.THROTTLE_MAX_RETRIES:
                    raise BedrockThrottlingError(
                        f"Bedrock throttled after {self.THROTTLE_MAX_RETRIES + 1} attempts"
                    ) from exc
                delay = min(
                    self.THROTTLE_BACKOFF_BASE * (2**attempt) + random.uniform(0, 1),
                    self.THROTTLE_MAX_DELAY,
                )
                time.sleep(delay)

        raise BedrockThrottlingError("Exhausted throttle retries")

    def _call_converse(self, system_message: str, prompt: str) -> str:
        """Single Bedrock Converse API call. Returns the assistant text."""
        kwargs: dict = {
            "modelId": self.model_id,
            "system": [{"text": system_message}],
            "messages": [
                {"role": "user", "content": [{"text": prompt}]},
            ],
            "inferenceConfig": {
                "maxTokens": 4096,
                "temperature": 0.1,
            },
        }

        # Add Guardrails config if configured
        if self.guardrail_id and self.guardrail_version:
            kwargs["guardrailConfig"] = {
                "guardrailIdentifier": self.guardrail_id,
                "guardrailVersion": self.guardrail_version,
            }

        response = self._client.converse(**kwargs)

        # Check for guardrail intervention
        stop_reason = response.get("stopReason", "")
        if stop_reason == "guardrail_intervened":
            trace = response.get("trace", {}).get("guardrail", {})
            raise BedrockGuardrailError(
                "Bedrock Guardrails blocked the request/response",
                action=trace.get("action", "BLOCKED"),
            )

        # Extract text from response
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])

        text_parts = []
        for block in content_blocks:
            if "text" in block:
                text_parts.append(block["text"])

        return "\n".join(text_parts)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        diffs: list[FileDiff],
        rules: list[Rule],
        registry: WebexAPIRegistryData | None = None,
    ) -> str:
        """Construct the analysis prompt from diffs, rules, and optional registry."""
        sections = []

        # Rules grouped by category
        rules_by_cat: dict[str, list[Rule]] = {}
        for rule in rules:
            rules_by_cat.setdefault(rule.category, []).append(rule)

        sections.append("## Review Rules\n")
        sections.append(
            "Analyze the code changes below against these security and quality rules. "
            "For each violation found, report it as a JSON finding.\n"
        )
        for cat, cat_rules in sorted(rules_by_cat.items()):
            sections.append(f"### Category: {cat}\n")
            for rule in cat_rules:
                sections.append(f"**{rule.id}**: {rule.description}")
                # Include the rule guidance (prompt text) for AI context
                if rule.prompt_or_pattern and len(rule.prompt_or_pattern) > 20:
                    # Truncate very long rule bodies to keep prompt manageable
                    body = rule.prompt_or_pattern[:2000]
                    if len(rule.prompt_or_pattern) > 2000:
                        body += "\n[... truncated]"
                    sections.append(f"\n{body}\n")
        # File diffs
        sections.append("## Changed Files\n")
        for diff in diffs:
            lang = diff.language or "unknown"
            sections.append(f"### File: `{diff.filename}` (language: {lang})\n")
            sections.append(f"```{lang}\n{diff.patch}\n```\n")

        # Webex API registry context (Phase 3, optional)
        if registry and registry.endpoints:
            sections.append("## Webex API Registry\n")
            sections.append(
                "The scaffold should reference at least one of these documented "
                "Webex Developer Platform API endpoints:\n"
            )
            for ep in registry.endpoints[:50]:  # Cap to keep prompt size reasonable
                sections.append(
                    f"- `{ep.method} {ep.path}` ({ep.technology}): {ep.description}"
                )

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # File batching
    # ------------------------------------------------------------------

    @staticmethod
    def batch_files(
        diffs: list[FileDiff], max_per_batch: int = 20
    ) -> list[list[FileDiff]]:
        """Split file diffs into batches of at most max_per_batch."""
        return [
            diffs[i : i + max_per_batch] for i in range(0, len(diffs), max_per_batch)
        ]
