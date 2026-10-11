Phase 1 is accepted, subject to the hardening checks below.

Do not begin the main Phase 2 implementation until these checks are complete and reported.

## Phase 1 hardening

1. Capture failure behavior
   - Confirm no storage, serialization, classification, or callback exception can escape into an unhandled HTTP 500.
   - Raw protected tool content must never fall through to model context.
   - Return the existing bounded, sanitized MCP-style error shape.
   - Automatic retry is not required because ADK cannot reach the retry path from `after_tool_callback`.
   - Add tests proving the returned error contains no artifact data and no exception escapes.

2. Configuration lookup failures
   - `_apply_materialization` may preserve availability when use-case lookup fails, but this must not be silent.
   - Add a structured warning and metric containing safe identifiers only.
   - Add tests for configuration lookup failure.
   - Confirm the result is either unchanged ordinary content or a literal unresolved placeholder, never partially materialized content.

3. Classifier thresholds
   - Keep current defaults for now, but centralize and validate them.
   - Document the defaults and their units.
   - Do not enable the feature in production until artifact row and byte limits are configurable or explicitly approved.

4. Cross-repository schema compatibility
   - The Orchestrator read-only `ArtifactPGStore` mirror must remain compatible with the Executor-owned table.
   - Add a contract test covering table name, required columns, data types, ownership fields, expiry, checksum, and artifact payload decoding.
   - Document the Executor as the schema owner.

5. Test evidence
   - Re-run both complete unit suites.
   - Report exact commands, passing/skipped/failed counts, and the names of any failures.
   - Preserve evidence showing the two Orchestrator `test_environment.py` failures occur on the clean baseline.
   - Run focused tests for capture, storage, materialization, plugin ordering, all response-builder branches, and feature-flag-off compatibility.

After these checks pass, proceed with Phase 2 only.

## Phase 2 scope

Implement follow-up artifact queries and session addressing:

- Add the `query_artifact` built-in tool.
- Enforce tenant, use-case, and session ownership on every read.
- Return the same generic not-found response for missing and unauthorized IDs.
- Record `last_displayed_artifacts` in session state.
- Resolve “row N” through frozen stable row IDs, never a live database offset.
- Return an ambiguity response when multiple displayed artifacts could match.
- Support bounded row lookup, column projection, filters, and pagination.
- Add deterministic server-side `sum`, `count`, `min`, and `max`.
- Enforce limits for rows, columns, response bytes, filter complexity, aggregate work, and execution time.
- Keep full artifact content outside model context.

## Required Phase 2 tests

- Query by artifact ID and artifact name.
- Query by stable row ID and displayed row number.
- Ambiguous “row N” across multiple tables.
- Cross-tenant, cross-use-case, and cross-session access denial.
- Byte-identical not-found responses for missing and unauthorized IDs.
- Expired artifact rejection.
- Row, column, byte, filter, and execution limits.
- Exact aggregate results over the complete stored dataset.
- Session continuation and interruption/resume behavior.
- Confirmation that narrow query results, not full artifacts, reach model context.
- Feature flag off remains behaviorally unchanged.
- Existing Executor and Orchestrator suites continue to pass apart from documented baseline failures.

Do not include physical cleanup scheduling or AG-UI placeholder rendering in Phase 2. Keep those as separately approved later phases.

Stop and report before implementation if the current code cannot support stable session addressing, authorization parity, or deterministic aggregation without changing an external API contract.