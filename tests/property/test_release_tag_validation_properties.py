"""Property-based tests for CodeGuard release tag validation (Property 16).

# Feature: github-pr-review-agent, Property 16: CodeGuard release tag validation
# Validates: Requirements 10.2
"""

from hypothesis import given, settings, assume
import hypothesis.strategies as st

from src.codeguard_loader import CodeGuardLoader

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid semver components (non-negative integers)
semver_parts = st.integers(min_value=0, max_value=999)

# Build valid semver tags like v1.2.3
valid_semver_tags = st.builds(
    lambda major, minor, patch: f"v{major}.{minor}.{patch}",
    major=semver_parts,
    minor=semver_parts,
    patch=semver_parts,
)

# Branch names that must be rejected
branch_names = st.sampled_from(["main", "latest", "develop", "master"])

# Arbitrary strings without the v-prefix pattern
arbitrary_non_tag_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=50,
).filter(
    lambda s: (
        not s.startswith("v")
        or not all(part.isdigit() for part in s[1:].split(".") if part)
        or s[1:].count(".") != 2
    )
)

# Tags with extra content (pre-release, extra segments)
tags_with_extra_content = st.one_of(
    # v1.2.3-beta, v1.2.3-rc1, etc.
    st.builds(
        lambda major, minor, patch, suffix: f"v{major}.{minor}.{patch}-{suffix}",
        major=semver_parts,
        minor=semver_parts,
        patch=semver_parts,
        suffix=st.sampled_from(["beta", "rc1", "alpha", "dev", "SNAPSHOT"]),
    ),
    # v1.2.3.4 (extra segment)
    st.builds(
        lambda major, minor, patch, extra: f"v{major}.{minor}.{patch}.{extra}",
        major=semver_parts,
        minor=semver_parts,
        patch=semver_parts,
        extra=semver_parts,
    ),
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

# **Validates: Requirements 10.2**


@given(tag=valid_semver_tags)
@settings(max_examples=100)
def test_valid_semver_tags_are_accepted(tag: str) -> None:
    """Valid semver tags (v1.2.3, v0.0.1, v99.99.99) are accepted."""
    assert CodeGuardLoader.validate_release_tag(tag) is True


@given(branch=branch_names)
@settings(max_examples=100)
def test_branch_names_are_rejected(branch: str) -> None:
    """Branch names (main, latest, develop, master) are rejected."""
    assert CodeGuardLoader.validate_release_tag(branch) is False


@given(value=arbitrary_non_tag_strings)
@settings(max_examples=100)
def test_arbitrary_strings_without_v_prefix_are_rejected(value: str) -> None:
    """Arbitrary strings without the v-prefix semver pattern are rejected."""
    import re

    assume(not re.match(r"^v\d+\.\d+\.\d+$", value))
    assert CodeGuardLoader.validate_release_tag(value) is False


@settings(max_examples=100)
@given(data=st.data())
def test_empty_strings_are_rejected(data: st.DataObject) -> None:
    """Empty strings are rejected."""
    assert CodeGuardLoader.validate_release_tag("") is False


@given(tag=tags_with_extra_content)
@settings(max_examples=100)
def test_tags_with_extra_content_are_rejected(tag: str) -> None:
    """Tags with extra content (v1.2.3-beta, v1.2.3.4) are rejected."""
    assert CodeGuardLoader.validate_release_tag(tag) is False
