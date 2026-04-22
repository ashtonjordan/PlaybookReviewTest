# Workflow Configuration Guide

This guide covers every configuration knob for the PR Review Agent GitHub Action,
including environment variables, IAM setup, CodeGuard versioning, and the
ecosystem catalog.

---

## 1. Required Environment Variables

These variables **must** be set for the agent to run. The workflow file
(`.github/workflows/pr-review.yml`) wires most of them automatically from
GitHub context expressions.

| Variable | Source | Description |
|---|---|---|
| `GITHUB_TOKEN` | `${{ secrets.GITHUB_TOKEN }}` | Auto-generated per workflow run. Used for all GitHub API calls (fetching PR files, posting comments, updating check runs). No manual setup needed. |
| `PR_NUMBER` | `${{ github.event.pull_request.number }}` | The pull request number being reviewed. |
| `PR_OWNER` | `${{ github.repository_owner }}` | The GitHub organization or user that owns the repository. |
| `PR_REPO` | `${{ github.event.repository.name }}` | The repository name (without the owner prefix). |
| `COMMIT_SHA` | `${{ github.event.pull_request.head.sha }}` | The head commit SHA of the PR. Used to attach the Check Run to the correct commit. |
| `CODEGUARD_CHECKOUT_PATH` | Workflow `env` block | Local filesystem path where the CodeGuard release is checked out (default: `codeguard`). |

If any of these are missing or empty, the agent exits immediately with a
non-zero status code.

## 2. Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BASE_BRANCH_CHECKOUT_PATH` | *(empty — skips ecosystem validation)* | Path where the base branch `.github/rules/` directory is checked out. When set, the agent loads the Webex Ecosystem Catalog for Tier 1/Tier 2 validation. |
| `BEDROCK_MODEL_ID` | *(empty — rule-based mode only)* | Amazon Bedrock model identifier (e.g., `anthropic.claude-3-haiku-20240307-v1:0`). When set, enables AI-powered analysis alongside rule-based pattern matching. |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock API calls. |
| `BEDROCK_GUARDRAIL_ID` | *(empty — no guardrails)* | Bedrock Guardrail identifier. When set together with `BEDROCK_GUARDRAIL_VERSION`, the agent attaches guardrail config to every Converse API call. |
| `BEDROCK_GUARDRAIL_VERSION` | *(empty — no guardrails)* | Bedrock Guardrail version string. Both `BEDROCK_GUARDRAIL_ID` and `BEDROCK_GUARDRAIL_VERSION` must be set for guardrails to activate. |

### Running in Rule-Based Mode Only

If you omit `BEDROCK_MODEL_ID` (or leave it empty), the agent skips AI analysis
entirely and runs only CodeGuard rule-based pattern matching plus ecosystem and
scaffold checks. No AWS credentials are needed in this mode.

## 3. GitHub Action Workflow Inputs

The workflow file uses top-level `env` variables to configure CodeGuard checkout
and Bedrock settings. These are not `workflow_dispatch` inputs — they are
environment constants defined at the workflow level.

| Env Variable | Example Value | Description |
|---|---|---|
| `CODEGUARD_RELEASE_TAG` | `v1.3.1` | Pinned release tag of the CodeGuard repository. See [CodeGuard Release Tag Configuration](#5-codeguard-release-tag-configuration) below. |
| `CODEGUARD_REPO` | `cosai-oasis/project-codeguard` | The `owner/repo` of the CodeGuard repository. |
| `CODEGUARD_CHECKOUT_PATH` | `codeguard` | Local path for the CodeGuard checkout. |
| `BASE_BRANCH_CHECKOUT_PATH` | `base-rules` | Local path for the base branch rules checkout. |
| `AWS_REGION` | `us-east-1` | AWS region passed to the agent. |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | Bedrock model ID passed to the agent. |

Repository-level variables (Settings → Secrets and variables → Actions →
Variables) are used for values that vary per deployment:

| Variable | Description |
|---|---|
| `AWS_ROLE_ARN` | The IAM role ARN for OIDC federation. The OIDC credential step is skipped when this is empty. |
| `BEDROCK_GUARDRAIL_ID` | Optional Bedrock Guardrail identifier. |
| `BEDROCK_GUARDRAIL_VERSION` | Optional Bedrock Guardrail version. |

## 4. IAM Setup Requirements

The agent authenticates to AWS using GitHub OIDC federation — no long-term
secrets are stored. Full setup instructions are in
[`docs/aws-oidc-setup.md`](aws-oidc-setup.md). Here is a summary:

### OIDC Provider

Register GitHub's OIDC provider in your AWS account (one-time, account-wide):

- **Provider URL:** `https://token.actions.githubusercontent.com`
- **Audience:** `sts.amazonaws.com`

### IAM Role

Create an IAM role with:

- **Trust policy** that allows `sts:AssumeRoleWithWebIdentity` from the GitHub
  OIDC provider, scoped to your repository:

  ```json
  {
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/YOUR_REPO:*"
      }
    }
  }
  ```

- **Permissions policy** with the minimum required actions:

  ```json
  {
    "Effect": "Allow",
    "Action": [
      "bedrock:InvokeModel",
      "bedrock:ApplyGuardrail"
    ],
    "Resource": "*"
  }
  ```

  `bedrock:ApplyGuardrail` is only needed if you configure Bedrock Guardrails.

### Workflow Integration

The workflow uses `aws-actions/configure-aws-credentials@v4`:

```yaml
- name: Configure AWS credentials via OIDC
  if: vars.AWS_ROLE_ARN != ''
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ vars.AWS_ROLE_ARN }}
    aws-region: ${{ env.AWS_REGION }}
```

The `if` guard means the step is skipped entirely when `AWS_ROLE_ARN` is not
configured, allowing rule-based-only mode with zero AWS setup.

## 5. CodeGuard Release Tag Configuration

The agent checks out CodeGuard rules from a **pinned release tag** to ensure
deterministic, auditable rule versions.

### Format

Release tags must follow strict semver: `v` followed by `MAJOR.MINOR.PATCH`.

- ✅ `v1.0.0`, `v1.3.1`, `v2.0.0`
- ❌ `main`, `latest`, `develop`, `master`, `1.3.1` (missing `v` prefix)

The agent validates the tag format at startup via
`CodeGuardLoader.validate_release_tag()`. Branch names and non-semver strings
are rejected.

### How to Pin a Version

Edit the `CODEGUARD_RELEASE_TAG` environment variable in
`.github/workflows/pr-review.yml`:

```yaml
env:
  CODEGUARD_RELEASE_TAG: "v1.3.1"
```

To upgrade, change the tag to a newer release and commit the workflow file.
This makes rule version changes explicit and auditable in your Git history.

### What Happens on Checkout Failure

If the specified tag does not exist in the CodeGuard repository, the
`actions/checkout` step fails and the entire workflow job fails. GitHub Actions
reports this as a job-level failure on the PR.

## 6. Ecosystem Catalog Setup

The Webex Ecosystem Catalog tells the agent which SDK packages, REST API
endpoints, widget layout patterns, and integration patterns are recognized
Webex Developer ecosystem signals.

### File Location

Place the catalog file in your repository at:

```
.github/rules/ecosystem-catalog.yaml
```

Supported filenames (checked in priority order):
1. `ecosystem-catalog.yaml`
2. `ecosystem-catalog.yml`
3. `ecosystem-catalog.json`

### File Format

The catalog is a YAML (or JSON) file with four top-level sections:

```yaml
sdk_packages:
  - name: "webex-js-sdk"
    language: "javascript"
    import_patterns:
      - "require\\(['\"]webex['\"]\\)"
      - "from ['\"]webex['\"]"
    technology: "Messaging"

  - name: "@webex/embedded-app-sdk"
    language: "javascript"
    import_patterns:
      - "@webex/embedded-app-sdk"
    technology: "Embedded Apps"

rest_endpoints:
  - path: "/v1/messages"
    method: "POST"
    technology: "Messaging"
    description: "Send a message to a room"

  - path: "/v1/rooms"
    method: "GET"
    technology: "Messaging"
    description: "List rooms"

manifest_patterns:
  - pattern_type: "agent_desktop_layout"
    detection_keys:
      - "area"
      - "comp"
    technology: "Contact Center"
    description: "Agent Desktop layout JSON"

integration_patterns:
  - pattern_type: "byova_grpc"
    detection_patterns:
      - "VoiceVirtualAgent"
      - "voicevirtualagent\\.proto"
    technology: "Contact Center"
    description: "BYOVA gRPC service definition"
```

All sections are optional — omit any section you don't need. The agent
gracefully handles missing sections by treating them as empty lists.

### Adding New Entries

The catalog is extensible. To recognize a new SDK, endpoint, or pattern, add
an entry to the appropriate section and commit to your default branch. The
change takes effect on the next PR review.

## 7. Base Branch Anti-Tampering

The ecosystem catalog is loaded from the **base branch** (e.g., `main`), not
from the PR branch. This prevents a contributor from weakening validation by
modifying the catalog in their own PR.

The workflow achieves this with a separate checkout step:

```yaml
- name: Check out base branch rules for ecosystem catalog
  uses: actions/checkout@v4
  with:
    ref: ${{ github.event.pull_request.base.ref }}
    path: ${{ env.BASE_BRANCH_CHECKOUT_PATH }}
    sparse-checkout: .github/rules/
    sparse-checkout-cone-mode: false
```

Key points:

- `ref` is set to the PR's **base branch** (`github.event.pull_request.base.ref`),
  not the PR head.
- `path` is a separate directory (`base-rules/`) so it doesn't conflict with
  the main repo checkout or the CodeGuard checkout.
- `sparse-checkout` limits the checkout to only `.github/rules/`, keeping it
  fast and minimal.

The CodeGuard Rule_Set is loaded from its own pinned-tag checkout
(`CODEGUARD_CHECKOUT_PATH`), and the Ecosystem Catalog is loaded from the
base branch checkout (`BASE_BRANCH_CHECKOUT_PATH`). These are two independent
checkout paths with different trust models:

| Source | Checkout Path | Trust Model |
|---|---|---|
| CodeGuard rules | `codeguard/` | Pinned release tag from external repo |
| Ecosystem catalog | `base-rules/` | Base branch of the Playbook repo |
| PR code | `.` (repo root) | Untrusted — this is what gets reviewed |
