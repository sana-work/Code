Phase 2 is provisionally accepted. Complete the following Phase 2 hardening before starting Phase 3.

## 1. Make limiting behavior explicit

Do not silently alter query semantics.

- Reject requests exceeding the filter-condition limit. Never silently omit filters.
- Reject unsupported aggregate names and invalid filter operators.
- Rows, columns, and response bytes may be truncated only when the response includes explicit metadata:
  - `truncated`
  - `truncation_reason`
  - `returned_rows`
  - `total_rows`, when known
  - `has_more`
  - `limits_applied`
- Aggregates must run over the full authorized filtered dataset, not a paginated or truncated subset.
- Add tests proving truncation metadata is deterministic and filters are never silently dropped.

## 2. Enforce or accurately describe the execution budget

The current execution-time budget is logged-only and must not be described as an enforced security limit.

Inspect the actual query implementation and choose one safe approach:

1. Add a real timeout/cancellation mechanism using an existing repository pattern; or
2. Bound the maximum work before execution using artifact size, row count, filter complexity, and aggregate limits.

If neither approach can safely stop excessive work, retain the metric but rename and document it as an observability budget, not a hard limit. Treat real timeout enforcement as a production-enablement gate.

Add tests for the selected behavior.

## 3. Make query limits configurable

Move the query limits into validated use-case metadata or the closest established configuration mechanism:

- Maximum returned rows
- Maximum requested columns
- Maximum response bytes
- Maximum filter conditions
- Maximum aggregate work
- Execution-time budget, if enforceable

Keep conservative defaults matching the current constants. Invalid configuration must fail safely and emit a structured warning without exposing artifact data.

## 4. Verify session addressing

Add or confirm tests proving:

- `last_displayed_artifacts` is capped deterministically.
- A newer display replaces the previous addressing context as documented.
- Multiple tables displayed in one turn produce an ambiguity result for an unqualified “row N.”
- “Row N” resolves through frozen stable row IDs, never the current list or database order.
- Session state contains references and display metadata only, never artifact content.
- Interrupted and resumed sessions retain sufficient addressing information.

## 5. Preserve authorization and non-disclosure

Reconfirm through black-box tests that:

- Missing, expired, cross-tenant, cross-use-case, and cross-session IDs return byte-identical generic not-found results.
- Table-name lookup cannot cross ownership boundaries.
- Aggregates, filters, and projections cannot bypass ownership checks.
- Errors and logs contain safe identifiers only, never artifact payloads.

## 6. Verification report

Run both full unit suites and report:

- Exact commands
- Passed, skipped, and failed counts
- Names and evidence for baseline failures
- New hardening tests added
- Any remaining deviations from the plan

Do not start Phase 3 if filter clipping remains silent or if an observability-only execution budget is represented as an enforced limit.

After this hardening passes, stop and request approval for Phase 3: Async, Hybrid, Resume, retry/idempotency, and durability testing. Physical cleanup scheduling and AG-UI placeholder rendering remain out of scope.