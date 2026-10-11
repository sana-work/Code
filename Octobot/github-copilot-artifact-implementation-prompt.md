# GitHub Copilot Prompt: Implement Deterministic Tool-Result Artifacts

You are working in a workspace containing both the Agent Executor and Agent Orchestrator repositories. Implement the deterministic tool-result artifact design described in `plan.md` incrementally, using the current code as the source of truth.

## Objective

Large deterministic tool results, including tables, multiple tables, long text, and reports, must not be copied through LLM context merely so they can appear unchanged in the final response.

The intended design is:

1. Capture eligible tool output through a verified Google ADK callback.
2. Keep exact, bounded scalar facts needed for current-turn reasoning in `llm_context`.
3. Store large deterministic content durably as tenant- and session-scoped artifacts.
4. Give the model only compact artifact references and exact placeholders.
5. Materialize placeholders deterministically only at the true client-delivery boundary.
6. Support later questions such as "tell me more about row 2" through a bounded, authorized `query_artifact` tool without returning the whole artifact to the model.

Read all of `plan.md` before changing code. Pay particular attention to sections 8, 13, 17, 18, 19, 23, and 25.

## Sources of truth

Use this precedence order when information conflicts:

1. Current repository code, repository instructions, dependency lock files, migrations, and tests.
2. Installed Google ADK source for the exact pinned version.
3. Existing cross-repository API and event contracts.
4. `plan.md` as the target architecture and risk register.
5. File names and line numbers quoted in `plan.md`, which are hints only and may be stale.

Do not implement an assumption merely because it appears in the plan. Verify it first. Document any mismatch and adapt the smallest safe implementation to the actual code.

## Non-negotiable engineering constraints

- Change only code required for the current phase.
- Preserve existing architecture, naming, dependency injection, database, migration, configuration, logging, and testing patterns.
- Do not perform unrelated refactoring, formatting, renaming, dependency upgrades, or cleanup.
- Do not overwrite, revert, or reformat unrelated working-tree changes.
- Do not introduce a new storage product or dependency.
- Do not change existing public request or response contracts without explicit approval.
- Keep the feature disabled by default.
- With the feature disabled, behavior must remain unchanged.
- Never use an LLM to classify, split, render, fetch, or merge artifact content. Those operations must be deterministic.
- Never log artifact payloads, secrets, authorization scope, or raw sensitive tool content in new logs, errors, or metrics.
- Never trust an artifact ID supplied by the model or client without tenant, use-case, session, expiry, type, and integrity validation.
- Never use `eval`, executable templates, recursive substitution, or unbounded regular expressions for materialization.
- Never use live SQL offsets to interpret conversational row numbers. Use stable row IDs frozen at capture time.
- Never allow materialized artifact bytes into ADK session history, a later model turn, another agent's prompt, or the Orchestrator output-generator prompt.
- Do not add Hybrid-specific behavior in Phase 1. First complete and verify Sync/Stream behavior.
- Do not implement multiple phases in one undifferentiated change.

## Mandatory Phase 0: inspect and verify before production edits

Perform Phase 0 first. Do not edit production code until the investigation below is complete.

### Repository and baseline inspection

1. Locate the Executor and Orchestrator repository roots and read their `AGENTS.md`, Copilot instructions, contribution guides, and test configuration.
2. Inspect the current working-tree status in both repositories. Preserve all pre-existing changes.
3. Identify the current branches and relevant recent streaming changes.
4. Discover the repository-native commands for formatting, linting, type checking, migrations, unit tests, integration tests, and full suites.
5. Run the smallest existing baseline tests around the files that Phase 1 will touch. Record pre-existing failures before making changes.

### Verify the current execution path

Trace and record the actual code path for:

- Tool registration and tool invocation.
- ADK plugin construction and plugin order.
- `after_tool_callback` invocation and return-value replacement.
- Tool-error callbacks and retry behavior.
- Session event persistence.
- Final model-event extraction.
- Structured response conversion.
- HTTP Sync response construction.
- Executor SSE event production and terminal `STEP_RESULT`.
- Executor-to-Orchestrator Sync streaming.
- Async Kafka execution and final response publication.
- Hybrid completion and configured Kafka/webhook delivery.
- Interruption and Resume.
- Orchestrator output-generator synthesis in both Sync and Async paths.

### Verify the exact ADK behavior

Inspect the installed source for the pinned Google ADK version and add a focused characterization test when practical. Confirm:

1. The exact `after_tool_callback` signature.
2. Whether a non-`None` callback return replaces the raw function response.
3. Whether plugin iteration stops after the first non-`None` return.
4. Which successful-tool callbacks are skipped after replacement.
5. Whether the replacement is what ADK persists in session history.
6. Whether persisted and yielded events share the same event object or representation.

Do not rely on documentation for a different ADK version.

### Resolve these blocking design decisions

Resolve each decision from current code and existing contracts. If any decision requires product, security, or architecture approval and cannot be answered from the repository, stop before production edits and report it clearly.

1. **Internal versus external response boundary**
   - Determine which Executor responses are final user deliveries and which are internal Orchestrator step results.
   - Do not materialize content before an internal result is sent to another model-based synthesis step.
   - Do not use a content heuristic to remove a table embedded inside an `answer` string.
   - Prefer an explicit compact internal representation and a separately materialized external representation.
   - If a response-contract change would be required, stop and request approval rather than hiding it in Phase 1.

2. **Plugin short-circuiting**
   - Prove that inserting the capture plugin does not prevent a required later callback from running.
   - If it would, use the smallest code-consistent composite callback or integration point. Do not silently skip existing behavior.

3. **Storage authorization and data classification**
   - Confirm which existing configuration authorizes durable storage of raw tool content.
   - Do not assume that `enable_audit_context_logging` grants or denies product artifact persistence unless its semantics explicitly say so.

4. **Migration ownership**
   - Locate the correct migration system and tenant-schema creation pattern.
   - Confirm indexes, JSON support, transaction handling, and cleanup ownership.

5. **Failure policy**
   - Decide whether capture-storage failure may expose the raw result to the model.
   - Describe that behavior accurately: raw fallback is availability-first and fail-open for artifact isolation.
   - If the data policy prohibits raw fallback, return a bounded failure without leaking the content.

6. **Idempotency**
   - Identify stable invocation and tool-call identifiers across client retry, Orchestrator retry, Kafka retry, interruption, and Resume.
   - Do not invent a unique key until those flows are traced.

### Phase 0 output

Provide a concise verification report containing:

- Actual relevant files and symbols in both repositories.
- Exact ADK version and confirmed callback semantics.
- Existing test commands and baseline results.
- Decision for the internal/external boundary.
- Decision for plugin ordering or composition.
- Decision for artifact storage authorization.
- Migration location and pattern.
- Failure policy.
- Proposed idempotency key or an explicit unresolved blocker.
- Any differences from `plan.md`.

If all mandatory gates are resolved from code, continue directly to Phase 1. If any gate is unresolved, stop without making production edits.

## Phase 1: Sync/Stream capture and current-turn materialization

Implement only Phase 1 after Phase 0 succeeds.

### Phase 1 scope

1. Add the minimum validated use-case configuration required to enable artifact capture, defaulting to disabled.
2. Add the tenant-routed durable artifact store and migration using the repository's existing Postgres store pattern.
3. Add deterministic result classification and canonicalization.
4. Add the verified ADK callback integration that:
   - Receives a successful tool result.
   - Extracts configured exact scalar fields into bounded `llm_context`.
   - Stores configured large content as one or more artifacts.
   - Returns only `llm_context` and bounded `artifact_refs` to the model.
   - Ensures raw stored artifact data is absent from ADK session history.
5. Add exact placeholder validation.
6. Add bounded, literal, single-pass materialization at the verified external boundary.
7. Support one table, multiple tables from one tool, tables from multiple tools, and large text.
8. Keep the existing Sync JSON route and Stream terminal-event contracts unchanged.
9. Do not implement `query_artifact`, aggregation, Async, Hybrid, Resume hardening, dashboards, or broad Orchestrator changes in this phase.

### Classification requirements

- Use explicit per-tool or per-use-case extraction rules where available.
- Preserve configured scalar facts verbatim. Do not summarize or transform them.
- Do not infer business-critical fields from generic size heuristics alone.
- Store canonical structured values, not rendered Markdown, when the original tool result is structured.
- Compute rendering only during materialization.
- Enforce maximum artifact size, row count, field count, nesting depth, and model-visible metadata size using existing limits where possible.
- For an unsupported or unclassified response, preserve current behavior and emit a bounded diagnostic. Do not silently discard data.

### Storage requirements

- Reuse current tenant resolution and connection lifecycle.
- Store opaque artifact ID, ownership, session/invocation/tool identity, kind, content type, version, order, size, checksum, canonical data, stable row IDs, timestamps, and expiry only where required by the approved schema.
- Use atomic writes for all artifacts produced by one tool result, or do not issue references for uncommitted rows.
- Add only indexes justified by read and cleanup paths.
- Do not expose internal storage keys to the model.

### Materialization requirements

- Accept only placeholders issued during the current invocation.
- Inspect only approved response fields.
- Replace tokens literally and non-recursively.
- Keep output schema valid. In Phase 1, prefer string-to-string rendering unless the existing schema explicitly supports structured data.
- Leave unknown or invalid placeholders unexpanded and emit a diagnostic without fetching arbitrary IDs.
- Verify checksums before materialization.
- Do not materialize an internal response that will enter another LLM prompt.

## Phase 1 testing protocol

Write focused tests with each small production change. Do not postpone all testing until the end.

At minimum, cover:

1. Feature flag off: behavior unchanged.
2. No artifact detected: behavior unchanged.
3. One table captured and materialized exactly.
4. Multiple tables from one tool call.
5. Artifacts from multiple tool calls with deterministic ordering.
6. Large text artifact.
7. Exact current-turn scalar such as `pay_date` remains available to the model.
8. Missing required scalar projection produces an explicit diagnostic rather than a guessed answer.
9. Oversized artifact creates no partial row.
10. Partial database failure creates no dangling placeholder.
11. Unknown, expired, foreign, stale, and wrong-type placeholder references are not expanded.
12. Repeated placeholders are deterministic and idempotent.
13. Raw artifact content is absent from persisted ADK session events.
14. Materialized content is absent from a later model turn.
15. Plugin-order behavior is proven by tests.
16. Existing audit behavior is either preserved exactly or changed only according to an approved decision.
17. Existing Sync JSON and Stream SSE tests pass with the feature disabled.
18. The terminal Stream result is materialized according to the approved transport contract.
19. Existing Orchestrator prompts receive no materialized bytes on every path enabled during this phase.

For every implementation step:

1. Run the new focused test.
2. Run adjacent subsystem tests.
3. Run repository formatting, lint, type, and migration validation.
4. Run the complete affected repository suite before declaring Phase 1 complete.
5. Run cross-repository contract tests for any boundary touched.

Do not weaken assertions, add broad skips, or modify unrelated tests to obtain a green build.

## Phase 1 completion checkpoint

Stop after Phase 1. Do not start Phase 2 in the same run.

Report:

- Decisions made during Phase 0.
- Files changed and why each was necessary.
- Database migration and rollback behavior.
- Tests added.
- Exact commands run and results.
- Proof that the flag-off path is unchanged.
- Proof that raw artifact bytes are absent from ADK history and later model context.
- Proof that Orchestrator model prompts do not receive materialized bytes for the implemented path.
- Any unresolved risks or deviations from `plan.md`.
- Recommended next phase.

## Later phases: execute only after explicit approval

### Phase 2

Add `query_artifact`, stable row addressing, `last_displayed_artifacts`, ambiguity handling, bounded projections/filters, authorization tests, and approved deterministic aggregates.

### Phase 3

Harden Async, Hybrid, Resume, Kafka/webhook delivery, retry/idempotency, expiry, cleanup, disconnect, cancellation, and process-restart behavior.

### Phase 4

Complete the verified Orchestrator internal/external representation and prompt-isolation work across synchronous and asynchronous synthesis paths.

For every later phase, repeat the same discipline: inspect first, make the smallest phase-scoped change, add focused tests with each step, run adjacent and full suites, and stop with a verification report before proceeding.

## Final implementation standard

The work is complete only when the relevant acceptance criteria in section 25 of `plan.md` are demonstrated by automated tests, not merely asserted in comments or documentation.
