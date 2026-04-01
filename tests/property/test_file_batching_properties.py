"""Property tests for file batching for large PRs.

Feature: github-pr-review-agent, Property 12: File batching for large PRs
Validates: Requirements 4.6
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from src.ai_model_client import AIModelClient
from src.models import FileDiff

# --- Strategies ---

languages = st.sampled_from(["python", "javascript", "typescript", "java", "go", None])

safe_filename = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="/_-."
    ),
    min_size=3,
    max_size=60,
).filter(lambda s: s.strip())

patch_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" +-@"
    ),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip())


@st.composite
def file_diffs(draw: st.DrawFn) -> FileDiff:
    return FileDiff(
        filename=draw(safe_filename),
        patch=draw(patch_text),
        language=draw(languages),
    )


# --- Property 12: File batching for large PRs ---


@given(diffs=st.lists(file_diffs(), min_size=21, max_size=120))
@settings(max_examples=100)
def test_batches_have_at_most_20_files(diffs):
    """Property 12: For any file list > 20, every batch should contain at most 20 files.

    **Validates: Requirements 4.6**
    """
    batches = AIModelClient.batch_files(diffs, max_per_batch=20)

    for batch in batches:
        assert len(batch) <= 20


@given(diffs=st.lists(file_diffs(), min_size=21, max_size=120))
@settings(max_examples=100)
def test_all_files_covered_across_batches(diffs):
    """Property 12: The union of all batches should contain every file from the
    original list, with the same total count.

    **Validates: Requirements 4.6**
    """
    batches = AIModelClient.batch_files(diffs, max_per_batch=20)

    flattened = [f for batch in batches for f in batch]
    assert len(flattened) == len(diffs)

    # Each file object appears in the flattened list at the same position
    for original, batched in zip(diffs, flattened):
        assert original is batched


@given(diffs=st.lists(file_diffs(), min_size=21, max_size=120))
@settings(max_examples=100)
def test_no_duplicate_files_across_batches(diffs):
    """Property 12: No file should appear in more than one batch.

    **Validates: Requirements 4.6**
    """
    batches = AIModelClient.batch_files(diffs, max_per_batch=20)

    seen_ids: set[int] = set()
    for batch in batches:
        for f in batch:
            obj_id = id(f)
            assert obj_id not in seen_ids, f"Duplicate file detected: {f.filename}"
            seen_ids.add(obj_id)


@given(diffs=st.lists(file_diffs(), min_size=0, max_size=20))
@settings(max_examples=100)
def test_small_lists_produce_single_batch(diffs):
    """Property 12 (supplementary): Lists with ≤ 20 files should produce exactly
    one batch (or zero batches for empty input) containing all files.

    **Validates: Requirements 4.6**
    """
    batches = AIModelClient.batch_files(diffs, max_per_batch=20)

    if len(diffs) == 0:
        assert batches == []
    else:
        assert len(batches) == 1
        assert batches[0] == diffs
