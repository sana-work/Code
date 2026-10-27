# Universal Chat: Response-Time Optimization

Prepared: 27 October 2026

## Applied Prompt Changes

- AS explicitly requests the smallest complete evidence set: every supported client-requested field, decisive facts for each question, needed identifiers, currencies and units. No default columns are assumed. Do not request unrelated fields as insurance or omit necessary evidence to save time.
- All independent AS/TM calls are planned upfront and submitted together, once per tool. No sequential fallback, extra-field lookup, automatic retry or second-page call is introduced.
- The agent follows one evidence-planning, validation and final-composition sequence, without extra planner, metadata or formatter calls for an executable request.
- Final delivery uses the runtime-registered set_model_response transport once when present, or a direct JSON response when absent, never both. The payload is checked before submission and error is explicitly initialized as a string. This targets avoidable invalid-payload correction rounds; it does not implement runtime event deduplication or prove a latency reduction.
- Client prose is concise and non-repetitive. Routine acknowledgements and retrieval announcements are omitted; requested facts, useful explanations, safety checks and mandatory TM sections remain.
- Tables have no fixed column cap. The ten-row display threshold and full-table override remain unchanged. Faster responses must not be achieved by dropping requested columns, source rows or relevant facts.

These changes target unnecessary work and payload size. A shorter prompt alone does not establish a meaningful latency reduction; large table outputs and slow tools may dominate. No production before/after timing has been measured, and no model, reasoning, timeout or backend setting has been changed.

Deployment prerequisite: expose the current AS output-field names and descriptions to the agent, without obsolete default-output wording. The prompt cannot discover fields that the registered schema does not describe. This update does not change input filters or assert that the production tool binding has been inspected.

## Runtime Recommendations: Not Yet Implemented

1. **Measure the actual bottleneck.** Capture end-to-end completion time, first-token time, pre-tool and post-tool model time, per-tool duration, queue time, concurrent-call overlap, prompt/output tokens and response bytes. First-token speed alone is insufficient when the UI needs a complete valid JSON object.
2. **Verify real parallel execution.** Ensure the runtime dispatches independent calls concurrently rather than executing a model-produced batch serially. Confirm through timestamps; request ordering does not prove overlap. Keep domain/service results separate.
3. **Avoid redundant model passes.** Do not add another model solely to format an answer or repeat validation already enforced deterministically. Preserve one final-response owner and the existing UI contract.
4. **Materialize tables deterministically where feasible.** The model can identify source column indices and relevant evidence; application code can copy those columns and every source row, apply only the approved zero-time date display, validate coverage/cell counts and assemble the same final schema. This is a proposed runtime change, not a capability delivered by the YAML. It requires integration and regression testing, including full-table follow-ups and punctuation/null fidelity.
5. **Use approved caching and connection reuse where supported.** Keep stable instructions/schema before dynamic context for any provider-supported prefix cache; verify support and data-handling policy for the actual deployment. Reuse authenticated connections/tokens only within their approved lifetime and isolation rules. Do not enable another provider or infer cache support from this document.
6. **Keep context relevant without losing evidence.** Retain instructions, exact active criteria, unresolved questions and required full source results for table views. Remove unrelated historical chatter through an approved context-management design. Never replace fresh operational evidence with cached answers; a pure table-view follow-up is the distinct permitted reuse case.

The general principles of parallel independent work, fewer unnecessary requests/tokens and deterministic processing are supported by [OpenAI's latency optimization guide](https://developers.openai.com/api/docs/guides/latency-optimization). That guidance is not proof of equivalent cache features or speedups in the current Vertex/R2D2 deployment.

## Acceptance Measurement

Use equivalent AS/TM questions, synthetic or approved UAT data, the same deployed model, comparable load and matched output requirements. Run repeated samples before and after; report median and P95 completed-response times, tool timings, token/byte counts and failures. Include narrow AS requests, more than six required columns, ten versus eleven rows, full-table views, mixed-domain calls, email replies, unknown values and error paths.

Promote only if measured latency improves without reducing field coverage, factual correctness, source fidelity, date/identifier handling or client-email quality. The local unit-test timings measure test code, not agent response speed. Changing the model or reasoning level, truncating output, weakening validation or lowering row/field coverage is not part of this update.
