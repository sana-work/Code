# Final Delivery: Prompt-Only Revision

27 October 2026

## Changes

The current YAML no longer prohibits the registered final-response transport. When set_model_response is registered as that transport, the agent is instructed to submit one complete validated payload through it and stop, without a direct JSON duplicate or completion message. If it is not registered, the agent returns the JSON object directly once. Finalization stays separate from the parallel business-call batch and toolsUsed; output serialization must not cause repeated AS/TM lookups.

Every payload now explicitly contains error as a string: exactly "" for SUCCESS, NEEDS_CLARIFICATION and OUT_OF_SCOPE; a safe non-empty code/message for FAILED. The older instruction to omit error on non-failed responses has been removed. The existing UI schema permits this string property and is unchanged, including its optional-property required list, response_type and output_key.

## Verification

- All 136 local tests passed: 101 existing checks and 35 new payload/schema/static prompt checks. See unit_tests.xml.
- The new tests cover empty versus null error values, FAILED error values, object versus encoded/wrapped arguments, finalizer exclusion from toolsUsed, mutually exclusive delivery instructions and preservation of source literal-null cells.
- Business instruction sections 2, 4, 5, 6, 7, 8 and 9 are unchanged from this follow-up's baseline. AS explicit output selection, filters, TM templates, date formatting, grounding and evidence-table behavior are preserved.
- UI schema SHA-256 remains c8a46ceac9cc5d2d733778373cec24f4c1cd6a5c2075a6a5a1e7a80f7867a51f. Prompt hashes are in verification.json. The baseline and current prompt are frozen separately in this folder; earlier snapshots and model observations are not rewritten.

These are finite local checks of payload compatibility and instruction invariants, not a live language-model test, native finalizer test, UI test, runtime-publication test or latency benchmark. They do not prove that the deployed model obeys the single-delivery instruction.

## Scope And UAT

Only the prompt, tests and accompanying guidance were changed. No executor, runtime retry, event publisher, UI or backend implementation was modified. The screenshot's first null error is incompatible with the local schema; that observation does not prove the executor's precise retry mechanism. A separate runtime publisher could still emit duplicate events despite a single correct model submission.

In a new UAT session, verify the deployed prompt revision, one finalization submission, string-valued error, no second direct answer, unchanged business-tool call count, complete evidence columns and date-only zero-time display. Check actual final events and completed-response timings; no duplicate-event fix or speed improvement is asserted by these local tests.

General reference: [OpenAI Docs on structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs) distinguishes schema formatting from possible answer mistakes. It does not define the Citi runtime's set_model_response behavior or establish that this deployment uses OpenAI Structured Outputs.
