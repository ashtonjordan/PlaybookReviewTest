"""Shared fixtures and Hypothesis strategies for the GitHub PR Review Agent tests."""

import hypothesis.strategies as st

from src.models import VALID_CATEGORIES, Finding, PRFile, Rule, RuleSet, Severity

# --- Hypothesis Strategies ---

severities = st.sampled_from(list(Severity))
categories = st.sampled_from(sorted(VALID_CATEGORIES))

# Non-empty, printable strings that survive YAML/JSON round-tripping cleanly.
safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"), whitelist_characters=" -_"
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())

rule_ids = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=1,
    max_size=40,
).filter(lambda s: s.strip())

file_extensions = st.lists(
    st.from_regex(r"\.[a-z]{1,6}", fullmatch=True),
    max_size=10,
)


@st.composite
def valid_rules(draw: st.DrawFn) -> Rule:
    """Generate a random valid Rule that passes ReviewRulesEngine.validate_rule()."""
    return Rule(
        id=draw(rule_ids),
        category=draw(categories),
        description=draw(safe_text),
        severity=draw(severities),
        prompt_or_pattern=draw(safe_text),
        enabled=draw(st.booleans()),
    )


@st.composite
def valid_rule_sets(draw: st.DrawFn) -> RuleSet:
    """Generate a random valid RuleSet."""
    rules = draw(st.lists(valid_rules(), min_size=0, max_size=15))
    version = draw(st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True))
    allowlist = draw(file_extensions)
    return RuleSet(rules=rules, version=version, file_allowlist=allowlist)


# --- File extension strategies for PromptGuard tests ---

# Extensions that ARE in the default allowlist
allowlisted_extensions = st.sampled_from(
    [
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
    ]
)

# Extensions that are NOT in the default allowlist
non_allowlisted_extensions = st.sampled_from(
    [
        ".md",
        ".txt",
        ".png",
        ".jpg",
        ".svg",
        ".gif",
        ".pdf",
        ".csv",
        ".yaml",
        ".json",
        ".html",
        ".css",
        ".xml",
    ]
)

pr_file_statuses = st.sampled_from(["added", "modified", "removed"])


@st.composite
def pr_files_with_extension(
    draw: st.DrawFn, extension: st.SearchStrategy[str] = allowlisted_extensions
) -> PRFile:
    """Generate a PRFile with a specific extension strategy."""
    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"), whitelist_characters="_-"
            ),
            min_size=1,
            max_size=30,
        ).filter(lambda s: s.strip())
    )
    ext = draw(extension)
    return PRFile(
        filename=f"src/{name}{ext}",
        status=draw(pr_file_statuses),
        additions=draw(st.integers(min_value=0, max_value=500)),
        deletions=draw(st.integers(min_value=0, max_value=500)),
        patch=draw(safe_text),
    )


@st.composite
def mixed_pr_file_lists(draw: st.DrawFn) -> list[PRFile]:
    """Generate a list of PRFiles with a mix of allowlisted and non-allowlisted extensions."""
    allowed = draw(
        st.lists(
            pr_files_with_extension(allowlisted_extensions), min_size=0, max_size=10
        )
    )
    not_allowed = draw(
        st.lists(
            pr_files_with_extension(non_allowlisted_extensions), min_size=0, max_size=10
        )
    )
    combined = allowed + not_allowed
    draw(st.randoms()).shuffle(combined)
    return combined


# --- Finding strategies for ReviewReportGenerator tests ---

file_paths = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="/_-."
    ),
    min_size=3,
    max_size=60,
).filter(lambda s: s.strip())


@st.composite
def valid_findings(draw: st.DrawFn) -> Finding:
    """Generate a random valid Finding."""
    line_start = draw(st.integers(min_value=1, max_value=500))
    line_end = draw(st.integers(min_value=line_start, max_value=line_start + 50))
    return Finding(
        file_path=draw(file_paths),
        line_start=line_start,
        line_end=line_end,
        rule_id=draw(rule_ids),
        category=draw(categories),
        severity=draw(severities),
        description=draw(safe_text),
    )
