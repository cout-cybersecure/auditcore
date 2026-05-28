# Policy bundle (OPA)

This directory holds the Rego policies that guard:

1. **Collector command allowlist** — what the Go collector is allowed to execute.
2. **Connector scope guards** — which resources a connector may read for a tenant.
3. **Action approval** — write-profile authorization (Phase 3).

In Phase 1 the collector ships with its allowlist compiled in (see [collector/internal/policy/allowlist.go](../collector/internal/policy/allowlist.go)). Phase 3 will load this Rego bundle at startup and signal-verify it against an AuditCore-controlled key.

## Files

| File | Purpose |
|---|---|
| [allowlist.rego](allowlist.rego) | The canonical read-only command allowlist. |
| [allowlist_test.rego](allowlist_test.rego) | Conformance tests. Run with `opa test policy/`. |

## Sync rule

`allowlist.rego` and the Go `policy.Phase1` slice MUST list the same tools. CI runs a check (see [.github/workflows/policy.yml](../.github/workflows/policy.yml)) that diffs the two and fails on drift.
