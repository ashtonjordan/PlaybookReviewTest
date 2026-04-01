"""Property-based tests for file allowlist filtering (Property 13).

# Feature: github-pr-review-agent, Property 13: File allowlist filtering retains only code files
# Validates: Requirements 9.1
"""

import os

from hypothesis import given, settings
import hypothesis.strategies as st

from src.models import PRFile
from src.prompt_guard import PromptGuard
from tests.conftest import (
    allowlisted_extensions,
    mixed_pr_file_lists,
    non_allowlisted_extensions,
    pr_files_with_extension,
    safe_text,
)

guard = PromptGuard()


# **Validates: Requirements 9.1**


@given(files=mixed_pr_file_lists())
@settings(max_examples=100)
def test_filtered_files_all_have_allowlisted_extensions(files: list[PRFile]) -> None:
    """All files in the filtered result have extensions in the allowlist."""
    result = guard.filter_files(files)
    for f in result:
        ext = os.path.splitext(f.filename)[1]
        assert ext in guard.file_allowlist, f"Extension {ext} not in allowlist"


@given(files=mixed_pr_file_lists())
@settings(max_examples=100)
def test_filtered_files_exclude_non_allowlisted_extensions(files: list[PRFile]) -> None:
    """No files in the filtered result have extensions NOT in the allowlist."""
    result = guard.filter_files(files)
    for f in result:
        ext = os.path.splitext(f.filename)[1]
        assert ext in guard.file_allowlist


@given(files=mixed_pr_file_lists())
@settings(max_examples=100)
def test_filtered_list_is_subset_of_original(files: list[PRFile]) -> None:
    """Filtered list is a subset of the original list (same objects)."""
    result = guard.filter_files(files)
    original_ids = {id(f) for f in files}
    for f in result:
        assert id(f) in original_ids, "Filtered file is not from the original list"


@given(files=mixed_pr_file_lists())
@settings(max_examples=100)
def test_all_allowlisted_files_are_retained(files: list[PRFile]) -> None:
    """All files from the original list that have allowlist extensions appear in the filtered result (completeness)."""
    result = guard.filter_files(files)
    expected = [
        f for f in files if os.path.splitext(f.filename)[1] in guard.file_allowlist
    ]
    assert result == expected


@given(
    custom_allowlist=st.frozensets(allowlisted_extensions, min_size=1, max_size=5),
    files=mixed_pr_file_lists(),
)
@settings(max_examples=100)
def test_custom_allowlist_filters_correctly(
    custom_allowlist: frozenset[str], files: list[PRFile]
) -> None:
    """A custom allowlist filters files according to its own extensions, not the default."""
    custom_guard = PromptGuard(file_allowlist=set(custom_allowlist))
    result = custom_guard.filter_files(files)
    for f in result:
        ext = os.path.splitext(f.filename)[1]
        assert ext in custom_allowlist
    expected = [f for f in files if os.path.splitext(f.filename)[1] in custom_allowlist]
    assert result == expected


@settings(max_examples=100)
@given(data=st.data())
def test_empty_file_list_returns_empty(data: st.DataObject) -> None:
    """Filtering an empty file list returns an empty result."""
    result = guard.filter_files([])
    assert result == []
