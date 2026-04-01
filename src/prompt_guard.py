"""PromptGuard: file allowlist filtering, prompt hardening, and output validation."""

import os
from src.models import PRFile


class PromptGuard:
    """Defends against prompt injection via file filtering, prompt hardening, and output validation."""

    DEFAULT_ALLOWLIST: set[str] = {
        ".py",
        ".js",
        ".ts",
        ".java",
        ".go",
        ".rb",
        ".rs",
        ".cpp",
        ".c",
        ".cs",
        ".kt",
        ".swift",
        ".sh",
    }

    def __init__(self, file_allowlist: set[str] | None = None):
        self.file_allowlist = (
            file_allowlist if file_allowlist is not None else self.DEFAULT_ALLOWLIST
        )

    def filter_files(self, files: list[PRFile]) -> list[PRFile]:
        """Filter PR files through the File_Allowlist. Returns only code files."""
        return [
            f for f in files if os.path.splitext(f.filename)[1] in self.file_allowlist
        ]

    def build_system_message(self) -> str:
        """Return the strict system message that constrains the AI to code analysis only.
        Stub for Phase 2."""
        raise NotImplementedError("Phase 2: AI integration")

    def validate_response_schema(self, response: dict) -> bool:
        """Validate that the AI response conforms to the expected JSON schema.
        Stub for Phase 2."""
        raise NotImplementedError("Phase 2: AI integration")
