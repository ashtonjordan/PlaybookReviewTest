# Test Scaffolds for Ecosystem Validation

These scaffolds test the PR Review Agent's Webex ecosystem detection signals.

| Scaffold | Expected Result | What it tests |
|---|---|---|
| `good-messaging-bot/` | PASS (no findings) | Python SDK import + actual usage |
| `good-rest-api-client/` | PASS (no findings) | REST API URLs with documented endpoints |
| `good-widget-layout/` | PASS (no findings) | Agent Desktop layout JSON with area/comp keys |
| `bad-import-only/` | WARNING | SDK imported but never used |
| `bad-no-webex/` | ERROR | No Webex ecosystem signals at all |
| `bad-undocumented-endpoint/` | WARNING | REST URL detected but endpoint not in catalog |
