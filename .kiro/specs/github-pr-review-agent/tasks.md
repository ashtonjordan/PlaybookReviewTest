# Implementation Plan: GitHub PR Review Agent

## Overview

Phased implementation of the GitHub PR Review Agent. Phase 1 delivers an MVP with rule-based pattern matching via GitHub Actions + CodeGuard rules (no AI). Phase 2 adds Bedrock AI integration. Phase 3 adds Webex API validation and scaffold checks. Phase 4 is optional polish and hardening.

## Tasks

### Phase 1: MVP — GitHub Action + CodeGuard Rules (Rule-Based Review)

- [x] 1. Set up project structure, data models, and testing framework
  - [x] 1.1 Create project directory structure (`src/`, `tests/unit/`, `tests/property/`, `tests/conftest.py`)
    - Create `src/__init__.py`, `src/models.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/property/__init__.py`
    - Install dev dependencies: `pytest`, `hypothesis`, `pyyaml`
    - _Requirements: 3.1_

  - [x] 1.2 Implement data models in `src/models.py`
    - Define `Severity` enum, `VALID_CATEGORIES` frozenset
    - Define `Rule`, `RuleSet`, `PRFile`, `FileDiff`, `Finding`, `ReviewReport`, `ReviewComment` dataclasses
    - Implement `ReviewReport.has_errors` property and verdict logic
    - _Requirements: 3.2, 3.4, 5.1, 5.2, 5.3_

- [x] 2. Implement ReviewRulesEngine
  - [x] 2.1 Create `src/review_rules_engine.py`
    - Implement `load()` to parse YAML/JSON Rule_Set files
    - Implement `validate_rule()` to check required fields (id, category, description, severity, prompt_or_pattern) and valid category values
    - Implement `filter_by_category()` and `get_enabled_rules()`
    - Implement `print_rule_set()` for YAML/JSON serialization
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 3.8, 3.9_

  - [x] 2.2 Write property test: Rule_Set round-trip serialization
    - **Property 1: Rule_Set round-trip serialization**
    - Generate random valid RuleSet objects, print to YAML/JSON, parse back, assert equivalence
    - **Validates: Requirements 3.1, 3.8, 3.9**

  - [x] 2.3 Write property test: Rule validation rejects incomplete/invalid rules
    - **Property 2: Rule validation rejects incomplete or invalid rules**
    - Generate Rules with missing/invalid fields, assert validation returns descriptive errors
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [x] 2.4 Write property test: Rule filtering by enabled flag and category
    - **Property 3: Rule filtering by enabled flag and category**
    - Generate RuleSets, filter by category and enabled, assert correct subsets
    - **Validates: Requirements 3.6, 3.7**

- [x] 3. Implement PromptGuard file allowlist filtering
  - [x] 3.1 Create `src/prompt_guard.py`
    - Implement `DEFAULT_ALLOWLIST` class attribute
    - Implement `__init__` accepting optional custom allowlist
    - Implement `filter_files()` to retain only files with extensions in the allowlist
    - Stub `build_system_message()` and `validate_response_schema()` (Phase 2)
    - _Requirements: 9.1, 9.2, 9.7_

  - [x] 3.2 Write property test: File allowlist filtering retains only code files
    - **Property 13: File allowlist filtering retains only code files**
    - Generate mixed-extension file lists, assert filtered list is correct subset
    - **Validates: Requirements 9.1**

- [x] 4. Implement ReviewReportGenerator and verdict logic
  - [x] 4.1 Create `src/report_generator.py`
    - Implement `generate()` to create ReviewReport from findings list
    - Verdict is "fail" if any finding has severity ERROR, "pass" otherwise
    - Summary counts findings grouped by severity
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.2 Write property test: Verdict is "fail" iff any finding has severity "error"
    - **Property 4: Review verdict is "fail" if and only if any finding has severity "error"**
    - Generate random Finding lists, assert verdict correctness
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 4.3 Write property test: Report summary counts match actual findings
    - **Property 5: Review report summary counts match actual findings**
    - Generate random Finding lists, assert summary counts equal actual counts per severity
    - **Validates: Requirements 5.4, 5.5**


- [x] 5. Implement StructuredLogger with secret redaction
  - [x] 5.1 Create `src/structured_logger.py`
    - Implement `__init__` with correlation_id
    - Implement `log()` to output structured JSON (correlation_id, level, message, timestamp)
    - Implement `redact()` to strip AWS keys, GitHub tokens, private key blocks, JWTs, connection strings, and password/secret/key/token/auth variable values
    - Apply redaction to all string fields before logging
    - _Requirements: 7.4, 7.5, 8.6_

  - [x] 5.2 Write property test: Secret redaction in log output
    - **Property 17: Secret redaction in log output**
    - Generate strings with embedded secret patterns, assert redacted output contains no secrets
    - **Validates: Requirements 7.5, 8.6**

  - [x] 5.3 Write property test: Structured JSON log output
    - **Property 18: Structured JSON log output**
    - Generate log calls, assert output is valid JSON with required fields
    - **Validates: Requirements 7.4**

- [x] 6. Implement GitHubAPIClient
  - [x] 6.1 Create `src/github_api_client.py`
    - Implement `__init__` with github_token
    - Implement `fetch_pr_files()` to call GitHub REST API for changed files and diffs
    - Implement `create_check_run()` to create/update Check Runs (pending, success, failure)
    - Implement `post_review_comments()` for inline review comments at file/line locations
    - Implement `post_review_summary()` for top-level PR summary comment
    - Add retry with exponential backoff (max 3 retries) on transient failures
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.2 Write property test: Verdict-to-check-status mapping
    - **Property 6: Verdict-to-check-status mapping**
    - Generate ReviewReports, assert "pass" → "success" and "fail" → "failure"
    - **Validates: Requirements 6.1, 6.2**

  - [x] 6.3 Write property test: Findings produce inline review comments at correct locations
    - **Property 7: Findings produce inline review comments at correct locations**
    - Generate ReviewReports with findings, assert each finding maps to a ReviewComment with matching file_path, line, and description
    - **Validates: Requirements 6.3**

- [x] 7. Implement retry decorator with exponential backoff
  - [x] 7.1 Create `src/retry.py`
    - Implement `with_retry` decorator with configurable max_retries, backoff_base, max_delay, and retryable_exceptions
    - Use exponential backoff with jitter: `delay = min(backoff_base * (2 ** attempt) + random.uniform(0, 1), max_delay)`
    - _Requirements: 2.3, 6.5, 7.2_

  - [x] 7.2 Write property test: Retry with exponential backoff on transient failures
    - **Property 8: Retry with exponential backoff on transient failures**
    - Simulate transient failures, assert retry count and increasing delays
    - **Validates: Requirements 2.3, 6.5, 7.2**

- [x] 8. Implement CodeGuardLoader (Rule_Set loading only)
  - [x] 8.1 Create `src/codeguard_loader.py`
    - Implement `__init__` with checkout_path and logger
    - Implement `load_rule_set()` to load and validate Rule_Set from the checked-out CodeGuard release directory
    - Implement `load_file_allowlist()` to extract configurable File_Allowlist from Rule_Set or return defaults
    - Stub `load_webex_registry()` (Phase 3)
    - _Requirements: 3.1, 9.7, 10.5_

- [x] 9. Wire MVP ReviewAgent orchestrator (rule-based, no AI)
  - [x] 9.1 Create `src/review_agent.py`
    - Implement `__init__` accepting all component dependencies
    - Implement `run()` pipeline for MVP:
      1. Set Check_Status to "pending"
      2. Fetch PR changed files via GitHubAPIClient
      3. Filter files through PromptGuard allowlist
      4. If no code files after filtering, set Check_Status "failure" with "no reviewable code found" and return
      5. Load Rule_Set via CodeGuardLoader
      6. Apply enabled rules as pattern matching against PR diffs
      7. Generate ReviewReport via ReviewReportGenerator
      8. Post inline comments and summary via GitHubAPIClient
      9. Update Check_Status to success/failure based on verdict
    - Wrap entire pipeline in try/except to set Check_Status "failure" on unhandled exceptions
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 5.1, 6.1, 6.2, 6.3, 6.4, 7.1, 9.1, 9.2_

  - [x] 9.2 Write property test: Unrecoverable errors set check status to failure
    - **Property 9: Unrecoverable errors set check status to failure**
    - Simulate unhandled exceptions, assert Check_Status set to "failure" and error logged
    - **Validates: Requirements 7.1**

- [x] 10. Create GitHub Action workflow file
  - [x] 10.1 Create `.github/workflows/pr-review.yml`
    - Trigger on `pull_request` events: opened, synchronize, reopened
    - Run on `ubuntu-latest`
    - Check out the Playbook repo
    - Check out CodeGuard repo at pinned release tag via `actions/checkout` with `ref` parameter
    - Configure CodeGuard release tag as workflow input / environment variable
    - Install Python dependencies
    - Run the ReviewAgent
    - Set `timeout-minutes` for job-level timeout
    - _Requirements: 1.1, 1.3, 1.4, 7.3, 10.1, 10.2, 10.3, 10.4_

- [x] 11. Checkpoint — Phase 1 MVP
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: rule loading, rule validation, file filtering, report generation, verdict logic, check status reporting, structured logging, and secret redaction all work end-to-end without AI.

### Phase 2: Bedrock AI Integration

- [ ] 12. Set up GitHub OIDC federation with AWS
  - [ ] 12.1 Create IAM infrastructure documentation or IaC snippet
    - Document IAM OIDC provider setup for GitHub Actions
    - Document IAM role with trust policy validating repo/workflow claims
    - IAM role permissions: `bedrock:InvokeModel`, `bedrock:ApplyGuardrail`
    - Add OIDC role assumption step to `.github/workflows/pr-review.yml` using `aws-actions/configure-aws-credentials`
    - _Requirements: 8.1, 8.2, 8.8_

- [ ] 13. Implement AIModelClient
  - [ ] 13.1 Create `src/ai_model_client.py`
    - Implement `__init__` with boto3_session, optional guardrail_id and guardrail_version
    - Implement `analyze()` to call Bedrock Converse API with system message and prompt
    - Include Guardrails config in Converse API call when guardrail_id is set
    - Retry up to 2 times on unparseable responses, 3 times on throttling (exponential backoff)
    - Parse AI response JSON and return structured dict
    - _Requirements: 4.1, 4.4, 4.5, 7.2_

  - [ ] 13.2 Implement `build_prompt()` in AIModelClient
    - Construct prompt from file diffs, enabled rules grouped by category, and Webex API registry context
    - Include only changed files, not entire repo
    - _Requirements: 4.1, 4.2_

  - [ ]* 13.3 Write property test: Prompt construction includes all required components
    - **Property 10: Prompt construction includes all required components and only changed files**
    - Generate diffs, rules, registry data; assert prompt contains all diffs, all rules, registry context, and no extra files
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 13.4 Write property test: AI response parsing produces structured findings
    - **Property 11: AI response parsing produces structured findings**
    - Generate well-formed AI response JSON, assert parsed Findings have all required fields
    - **Validates: Requirements 4.3**

  - [ ]* 13.5 Write property test: File batching for large PRs
    - **Property 12: File batching for large PRs**
    - Generate file lists > 20, assert batches ≤ 20 each, all files covered, no duplicates
    - **Validates: Requirements 4.6**

- [ ] 14. Implement PromptGuard system prompt hardening and output validation
  - [ ] 14.1 Complete `build_system_message()` in `src/prompt_guard.py`
    - Construct strict system message constraining AI to code security/quality analysis only
    - Include directives to ignore instructions in code comments, string literals, non-code content
    - _Requirements: 9.3_

  - [ ] 14.2 Complete `validate_response_schema()` in `src/prompt_guard.py`
    - Validate AI response conforms to expected JSON schema (findings array with file_path, line_number, rule_id, severity, description)
    - Return True/False; discard non-conforming responses
    - _Requirements: 9.5_

  - [ ]* 14.3 Write property test: System prompt hardening constrains AI to code analysis
    - **Property 14: System prompt hardening constrains AI to code analysis**
    - Assert system message contains constraint directives and ignore-injection instructions
    - **Validates: Requirements 9.3**

  - [ ]* 14.4 Write property test: Output JSON schema validation
    - **Property 15: Output JSON schema validation**
    - Generate valid/invalid response dicts, assert schema validator accepts/rejects correctly
    - **Validates: Requirements 9.5**

- [ ] 15. Integrate AI analysis into ReviewAgent pipeline
  - [ ] 15.1 Update `src/review_agent.py` to include AI path
    - After allowlist filtering, assume IAM role via OIDC
    - Build hardened prompt via PromptGuard.build_system_message()
    - Batch files (≤20 per batch) for large PRs
    - Invoke AIModelClient.analyze() per batch
    - Validate each AI response via PromptGuard.validate_response_schema()
    - Handle Bedrock Guardrails intervention (discard response, set Check_Status "failure")
    - Merge AI findings with rule-based findings into single ReviewReport
    - _Requirements: 4.1, 4.3, 4.6, 9.3, 9.4, 9.5, 9.6_

- [ ] 16. Update GitHub Action workflow for Bedrock
  - [ ] 16.1 Update `.github/workflows/pr-review.yml`
    - Add OIDC permission (`id-token: write`)
    - Add AWS credential assumption step
    - Pass Bedrock Guardrail ID/version as environment variables
    - _Requirements: 8.1, 8.2, 9.4_

- [ ] 17. Checkpoint — Phase 2 AI Integration
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: OIDC auth, Bedrock invocation, prompt construction, response parsing, schema validation, guardrails handling, and batching all work correctly.

### Phase 3: Webex API Validation + Scaffold Checks

- [ ] 18. Implement WebexAPIRegistry
  - [ ] 18.1 Create `src/webex_api_registry.py`
    - Implement `load()` to parse Webex API registry from YAML/JSON file in CodeGuard release
    - Implement `lookup()` to find endpoint by path and optional HTTP method
    - Implement `extract_api_references()` to extract API URLs/paths/methods from code strings
    - Implement `validate_references()` to check extracted references against registry; return "warning" for undocumented endpoints, "error" if no Webex API references found at all
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [ ]* 18.2 Write property test: Webex API reference extraction and validation
    - **Property 20: Webex API reference extraction and validation**
    - Generate API references and registries; assert undocumented → "warning", no matches → "error"
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

- [ ] 19. Implement ScaffoldChecker
  - [ ] 19.1 Create `src/scaffold_checker.py`
    - Implement `check_entry_point()` — "error" if no main/handler/script found
    - Implement `check_dependency_manifest()` — "warning" if no package.json/requirements.txt/etc.
    - Implement `check_config_references()` — "warning" for hardcoded URLs/ports/hostnames
    - Implement `check_syntax()` — findings for syntax errors or incomplete code blocks
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 19.2 Write property test: Scaffold runnability checks
    - **Property 21: Scaffold runnability checks**
    - Generate file sets with/without entry points, manifests, config refs; assert correct findings
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7**

- [ ] 20. Complete CodeGuardLoader for Webex registry
  - [ ] 20.1 Implement `load_webex_registry()` in `src/codeguard_loader.py`
    - Load WebexAPIRegistryData from the checked-out CodeGuard release directory
    - _Requirements: 10.5, 11.1, 11.6_

- [ ] 21. Integrate Webex validation and scaffold checks into ReviewAgent
  - [ ] 21.1 Update `src/review_agent.py`
    - After loading Rule_Set, load Webex_API_Registry via CodeGuardLoader
    - Run WebexAPIRegistry.extract_api_references() and validate_references() on PR code
    - Run ScaffoldChecker checks (entry point, dependency manifest, config references, syntax)
    - Merge Webex and scaffold findings into the ReviewReport alongside rule-based and AI findings
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 22. Checkpoint — Phase 3 Full Pipeline
  - Ensure all tests pass, ask the user if questions arise.
  - Verify: Webex API registry loading, API reference extraction, scaffold checks, and full pipeline integration all work end-to-end.

### Phase 4 (Optional): Polish and Hardening

- [ ] 23. Input sanitization and tag validation
  - [ ]* 23.1 Implement input sanitization in `src/prompt_guard.py` or `src/review_agent.py`
    - Sanitize/reject PR-derived inputs with injection characters (newlines, null bytes, control chars, excessively long strings)
    - _Requirements: 8.4_

  - [ ]* 23.2 Write property test: Input sanitization rejects malicious payloads
    - **Property 19: Input sanitization rejects malicious payloads**
    - Generate strings with injection characters, assert sanitization or rejection
    - **Validates: Requirements 8.4**

  - [ ]* 23.3 Implement CodeGuard release tag format validation
    - Validate ref string matches release tag pattern (e.g., `v1.2.3`), reject `main`, `latest`, `develop`, or arbitrary strings
    - _Requirements: 10.2_

  - [ ]* 23.4 Write property test: CodeGuard release tag validation
    - **Property 16: CodeGuard release tag validation**
    - Generate valid tags and branch names, assert correct accept/reject
    - **Validates: Requirements 10.2**

- [ ] 24. Enhanced error handling and documentation
  - [ ]* 24.1 Review and harden error handling across all components
    - Ensure all unhandled exceptions in ReviewAgent set Check_Status to "failure"
    - Tune retry parameters based on testing
    - _Requirements: 7.1_

  - [ ]* 24.2 Create workflow configuration guide
    - Document workflow inputs, environment variables, IAM setup, and CodeGuard release tag configuration
    - _Requirements: 10.3_

- [ ] 25. Final checkpoint — All phases complete
  - Ensure all tests pass, ask the user if questions arise.
  - Full end-to-end verification of rule-based review, AI analysis, Webex validation, scaffold checks, and all guardrails.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Phase 1 is independently deployable — it works end-to-end with rule-based pattern matching, no Bedrock or Webex validation needed
- Phase 2 adds AI-powered analysis on top of Phase 1's rule-based foundation
- Phase 3 adds Webex-specific and scaffold-specific validation
- Phase 4 is entirely optional hardening and polish
- Each phase has a checkpoint task for incremental validation
- Property tests validate universal correctness properties from the design document
- All code is Python, using pytest + Hypothesis for testing
