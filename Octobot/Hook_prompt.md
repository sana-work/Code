Phase 2 and its hardening pass are accepted. Proceed with Phase 3: Async, Hybrid, Resume, retry/idempotency, and durability hardening.

Do not implement physical cleanup scheduling or AG-UI placeholder rendering in this phase.

## Phase 3 objectives

Prove that artifact capture, compact transport, final materialization, session addressing, and follow-up queries remain correct across process boundaries, interruption/resume, retries, cancellation, and partial failures.

## 1. Async and Hybrid execution

Trace and test the complete production paths before changing code:

- Executor capture inside the Kafka/background-worker execution.
- Compact result publication to Kafka.
- Orchestrator consumption and response synthesis.
- Final materialization at the established external response boundary.
- Hybrid request initiation and Kafka-delivered final response.

Requirements:

- Kafka messages must contain only `llm_context`, `artifact_refs`, placeholders, and safe metadata.
- Raw or materialized artifact data must never enter Kafka step payloads, synthesis prompts, or ADK session history.
- A different process must be able to retrieve the committed artifact using tenant-routed storage.
- Async and Hybrid final responses must materialize identically to Sync.
- Feature-flag-off behavior must remain unchanged.

## 2. Resume and process restart

Verify both persistent and serialized in-memory session paths.

- An artifact captured before interruption remains queryable after resume.
- `last_displayed_artifacts` survives session serialization and rehydration.
- Stable row IDs remain unchanged after restart.
- Resume does not recapture completed tool calls.
- New tool calls triggered after resume may create new artifacts normally.
- Expired artifacts return the standard generic not-found result.
- Materialized client content must not be serialized back into session history.

Use a newly constructed store/service instance in tests to prove durability rather than relying on an existing in-process singleton or cache.

## 3. Idempotency and concurrent retries

Use the established key:

`invocation_id + function_call_id + artifact_sequence`

Required behavior:

- Retrying the same tool call does not create duplicate artifact rows.
- A repeated call returns or resolves to the same logical artifact/version deterministically.
- Different invocation IDs remain independent.
- Multiple artifacts from one tool call retain deterministic sequence and display order.
- Concurrent duplicate writes produce one durable logical result without leaking a uniqueness error.
- Retry after process restart behaves the same as retry in the original process.

Do not silently overwrite an artifact with different content under the same idempotency key. Detect the checksum conflict, log it safely, and return a bounded failure.

## 4. Transaction and partial-failure behavior

When one tool call produces multiple artifacts:

- Persist the capture atomically when supported by the current store pattern.
- A mid-capture failure must not leave a compact response referring to missing or partially written artifacts.
- If atomic multi-row persistence cannot be implemented without a broad redesign, clean up successfully written rows before returning the sanitized failure and document the residual risk.
- No raw tool content may fall through to the model after failure.
- No handled storage failure may become an unhandled HTTP 500.

Add fault-injection tests for first-write, middle-write, and final-write failures.

## 5. Cancellation and disconnect behavior

Test cancellation or client disconnect after:

- Tool completion but before artifact commit.
- Artifact commit but before compact response creation.
- Compact response creation but before final materialization.
- Final materialization but before delivery.

Requirements:

- Committed artifacts remain durable.
- Incomplete transactions are rolled back.
- Client retry is idempotent.
- No unbounded duplicate rows are created.
- No materialized artifact content is written into internal session or transport payloads.

## 6. Soft retention behavior

Physical cleanup remains out of scope, but soft expiry must work in every mode:

- Expired artifacts are excluded from direct lookup, name lookup, materialization, and `query_artifact`.
- Expiry behavior remains generic and non-disclosing.
- A resume after expiry cannot revive or expose the artifact.
- Retention configuration is resolved consistently after process restart.

## 7. Authorization parity

For Sync, Stream, Async, Hybrid, and Resume, confirm:

- Tenant, use-case, and session ownership are enforced before content is returned.
- Missing and unauthorized artifacts remain byte-identical externally.
- Table-name lookup cannot cross an ownership boundary.
- Logs, metrics, Kafka payloads, and errors never contain artifact data.

## Required tests

Add focused tests covering:

- Async capture and compact Kafka publication.
- Async final response materialization.
- Hybrid capture and materialization.
- Restart using a fresh store instance.
- Interruption/resume with preserved addressing state.
- Duplicate retry before and after restart.
- Concurrent duplicate capture.
- Same idempotency key with conflicting content.
- Multi-artifact atomicity and injected write failures.
- Disconnect/cancellation at each lifecycle point.
- Expiry before and after resume.
- Authorization and non-disclosure in every execution mode.
- Feature flag off in Async, Hybrid, and Resume.
- Existing Sync and Stream behavior remains unchanged.

Prefer existing repository fixtures and execution coordinators. Do not invent a parallel runtime or transport abstraction solely for these tests.

## Verification report

Run the complete Executor and Orchestrator unit suites and provide:

- Exact commands.
- Passed, skipped, and failed counts.
- Names and evidence for any baseline failures.
- A file-by-file change summary.
- Proof that Kafka/session payloads remain compact.
- Proof that retry and concurrency tests do not create duplicate rows.
- Any behavior that could not be verified without a real Postgres or Kafka integration environment.

Stop after Phase 3 and request approval before beginning Phase 4 rollout and Orchestrator hardening.