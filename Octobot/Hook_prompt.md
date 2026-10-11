Phase 3 is provisionally accepted. Proceed with Phase 4: production readiness, Orchestrator hardening, migration planning, and controlled rollout.

Do not enable artifact capture in production until every mandatory gate below is satisfied.

## 1. Resolve the database migration blocker

`Base.metadata.create_all()` does not add `idempotency_key` to an existing table.

Create an idempotent, production-reviewed database change for every tenant schema:

- Add nullable `idempotency_key`.
- Add the required unique or partial unique index.
- Use `IF NOT EXISTS` or the platform's established equivalent.
- Keep existing rows valid.
- Document database-first deployment ordering.
- Confirm old application versions tolerate the expanded schema.
- Provide verification and rollback queries.
- Add schema inspection or migration contract tests.

Do not rely on runtime `create_all()` to upgrade an existing table.

## 2. Close the missing-ID idempotency gap

The current implementation permits `idempotency_key = None` when invocation or function-call IDs are unavailable.

Trace all Sync, Stream, Async, Hybrid, and Resume paths and report whether both identifiers are guaranteed.

- If guaranteed, validate them before capture and add tests for every mode.
- If not guaranteed, stop and propose a deterministic fallback with collision analysis.
- Do not silently persist retry-sensitive artifacts without idempotency protection.
- Missing identifiers must emit a safe metric and follow an explicitly documented failure policy.

## 3. Add real integration verification

Unit simulations are necessary but insufficient for the concurrency and transport claims.

Using existing project infrastructure where available, test against real Postgres:

- Concurrent inserts for the same idempotency key.
- Same key and checksum resolves to one artifact.
- Same key and different checksum fails safely.
- Multi-artifact transaction rollback.
- Cancellation during a transaction.
- Fresh-process retrieval and soft expiry.
- Tenant-schema isolation.
- Index and constraint behavior after migration.

Verify with a real Kafka environment or staging deployment when available:

- Published step payloads contain compact references only.
- Raw artifact data never enters Kafka.
- Async materialization occurs before the final response is delivered.
- Duplicate message delivery remains idempotent.
- Broker and consumer restart behavior is safe.

If these environments are unavailable, create repeatable integration test commands and mark production enablement blocked. Do not describe mocked tests as live integration proof.

## 4. Harden every Orchestrator response boundary

Create one clearly owned final-response materialization interface and ensure it covers:

- Single-step raw response.
- Multi-step raw last-step response.
- Output-generator synthesis response.
- Async Kafka final-response branch.
- Hybrid response path.
- Error and unresolved-reference paths.

Requirements:

- `prepare_response()` and all synthesis prompts receive compact data only.
- Materialization happens after synthesis and before external delivery.
- Feature flag off performs no artifact lookup.
- Configuration lookup failures are logged and metered safely.
- Missing, unauthorized, expired, and failed lookups remain unexpanded and non-disclosing.
- Future response branches should be difficult to add without passing through the final materialization interface.

Add branch and contract tests for every boundary.

## 5. Production observability

Add or confirm metrics for:

- Capture success and failure.
- Capture failure reason.
- Idempotency reuse and checksum conflict.
- Batch rollback.
- Materialization success, missing reference, expired reference, and lookup failure.
- Query success, rejection, truncation, authorization denial, and ambiguity.
- Configuration fallback.
- Artifact rows and bytes written.
- Materialized response size and latency.
- Soft-expired rows still awaiting physical cleanup.

Metrics and logs must contain safe identifiers only, never artifact data.

## 6. Security and retention gates

Before production enablement, obtain explicit approval for:

- Artifact data classification.
- Tenant and session authorization rules.
- Database encryption and access.
- Audit behavior.
- Default retention period.
- Maximum artifact size.
- Incident and deletion procedures.

Physical cleanup scheduling remains outside this code phase, but unrestricted rollout is blocked without an operational deletion mechanism.

A small canary may proceed only if:

- The capture volume is strictly bounded.
- Soft expiry is enforced.
- Database growth is monitored.
- A tested manual cleanup procedure exists.
- Security and data-retention owners approve the exception.

## 7. Controlled rollout

Keep `enable_artifact_capture = False` by default.

Use these stages:

1. Automated and integration validation.
2. Shadow observation without changing client responses, if safely supported.
3. One approved internal pilot use case.
4. Limited canary with monitored volume.
5. Gradual opt-in expansion.
6. General availability only after cleanup and operational gates are complete.

Define rollback triggers for:

- Artifact leakage into prompts, sessions, or Kafka.
- Authorization mismatch.
- Materialization failure rate.
- Idempotency conflicts.
- Database growth.
- Response latency or size regression.

Rollback must be possible by disabling the feature flag without requiring an application downgrade.

## 8. Final verification

Run both complete unit suites plus available Postgres and Kafka integration suites.

Report:

- Exact commands and results.
- File-by-file changes.
- Migration and deployment order.
- Evidence for every response branch.
- Evidence that internal payloads remain compact.
- Real versus simulated integration coverage.
- Security and retention approvals still outstanding.
- Rollout and rollback runbooks.
- Any remaining production blocker.

Do not implement AG-UI placeholder rendering in Phase 4.

Stop after the Phase 4 report. Do not enable a production use case, create commits, or begin cleanup/AG-UI work without separate approval.