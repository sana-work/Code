# Prompt Testing Findings

## Outcome

**47 of 50 live synthetic first-attempt trials passed. Three failed the stricter presentation-wording check; their table data is correct.** Across 1,662 automated checks, three checks failed. The evaluator's **24 unit tests passed**, including deliberate mutations that drop rows/columns, change commas, rename headers, blank values, duplicate final responses, use table-position wording, and put text after the evidence appendix.

The production prompt was not modified during testing. Its file hash is `87d60f885b3ed3f1512147fe57d1bec937fe53121ef68bc5bcc756885529ce90`. The original decoded UI schema hash remains `c8a46ceac9cc5d2d733778373cec24f4c1cd6a5c2075a6a5a1e7a80f7867a51f`.

This is evidence from a finite synthetic test set, **not a guarantee of complete coverage or production readiness**. The actual production model, native tool bindings, authentication, email sending, and UI rendering were not tested. The API adapter was unit-tested with a stub provider, not a live API model.

## Findings

**Low severity: two confirmed table-position wording violations and one conservative introductory-wording flag.**

- `as_full_followup_uses_original_cache`: "is shown below, with all original source columns and values".
- `as_full_followup_cache_missing_requery`: "The full returned table, including every source column, is shown below."
- `si_unsupported_price`: "The Settlement Instruction details for client reference SYN-CLIENT-01 are provided below."

Section 8 prohibits describing a table's position. The two full-table replies correctly preserve the complete source table, identify whether the information was refreshed, and put the titled evidence appendix last. The SI wording refers generally to the details, not explicitly to a table; its classification is a conservative presentation flag, not a substantiated operational error. Remove the unnecessary positional lead-in in future outputs. A direct statement that supporting information is provided avoids "above", "below", or a table number. The saved first-attempt replies were not edited or rerun.

Two bounded model reviews found no substantiated unsupported operational claims in the reviewed answers. One reviewer initially self-reviewed twelve of its own responses; a second reviewer independently checked those twelve and the fourteen added cases. These reviews are useful additional evidence, not a comprehensive truth guarantee.

## What Was Exercised

| Area | Observed behavior |
| --- | --- |
| Final delivery | One UI response object per completed case; no second final answer or delivery-tool call. |
| Grounding | Cash, tax, and delivered shares use their own decisive fields; a passed Payment Date is not payment confirmation. Opaque TM status codes are not expanded. |
| Missing values | Null tax/status information and a blank cash amount stay unknown; numeric zero remains a valid amount. |
| Evidence tables | Ten rows produce compact evidence; eleven suppress tables and offer a view. Explicit full-table requests override both caps and preserve every returned column, row, and cell. |
| Cell fidelity | Full tables preserve blanks, `null`, trailing commas, quotes, newlines, Unicode, and a literal `null grandson` when that complete string exists in the source. |
| Parallel execution | Generic TM client-reference searches use all three applicable TM tools in one batch; mixed AS/TM can use all four once each. |
| Partial outcomes | An AS success survives a Current timeout. Invalid AS input does not discard independently valid TM work. |
| Client emails | Email-shaped input is recognized without an explicit reply instruction or subject. Existing subjects, known sender names, closing, and summary-before-evidence order are preserved. |
| Safety and errors | Source-cell instructions are not followed; unsupported HTML styling does not override the business response. Timeout, missing identity, malformed rows, missing status, and unavailable tools produce safe outcomes without retries. |
| Dates and context | Near-midnight local date resolution, missing runtime timestamp, contractual versus execution date, unsupported date ranges, cached full-table follow-ups, missing-cache requery, client bounds, and next-page scope were exercised. |

See `evaluation.md` for per-case results, `client_examples.json` for selected final UI payloads, and `live/` for the complete call/result/response traces. `run_manifest.json` records hashes and execution provenance.

## Test Expectation Corrections

The initial 36-case grading pass showed six false positives. We preserved those original first-attempt responses and the original catalogue/report; no failing answer was rewritten to manufacture a pass.

- The MT566 check incorrectly used a word boundary before an ISO time following `T`. It now checks the exact returned timestamp.
- The MT564 limitation check omitted the valid wording "does not confirm".
- Two intended AS full-table questions named only an account/ISIN, with no domain context. The agent correctly asked which domain was intended. Those questions remain ambiguity tests; two new, explicitly scoped AS cases exercise the intended full-table behavior.
- The no-data check omitted the valid wording "No cash payment records matched".
- The partial-success expectation incorrectly required a root `error`. The unchanged UI contract requires it only for `FAILED`; the safe failed-service outcome remains in the partial reply.

The suite was then expanded with twelve further boundary cases. A semantic review found the two table-position wording violations that the initial evaluator did not check; a new regression check now reports them and one conservative SI wording flag as failures. Scores reflect the corrected expectations for unchanged inputs plus the fourteen new first-attempt trials. Automated checks use selected factual assertions and exact structural comparisons; they are not a complete natural-language truth verifier.

## Remaining Risk

Before release, repeat these tests with the actual model and native runtime, then verify the UI treats full-table cells as inert text. Code-assisted copying in these Codex trials does not prove that an unaided deployed LLM can reproduce large arrays reliably. Duplicate UI messages may also arise from runtime delivery configuration, which this prompt-only test cannot observe.

Resolve the synthetic SI `trade_date` description before substituting production schemas: the fixture field description says "trade date associated with the instruction", while the tool description and tested prompt define it as that service's settlement-date equivalent. No trial claimed actual settlement from this date, but the deployed mapping must be explicit and consistent.

The mock backend describes default date windows but does not execute a full calendar/window engine. Tests verify returned notices, argument choices, and honest response qualification, not the correctness of production date-window coverage.

Further coverage is needed for invalid/positive/fractional timezone offsets, daylight-saving transitions, week/month conventions, conflicting history, unknown pagination metadata, multiple currencies, invalid numeric/timestamp strings, zero-row `SUCCESS`, tool-returned clarification choices, dependent lookups, and additional injection surfaces. Use repeated trials and human review; do not treat one perfect pass rate as proof that all unseen client enquiries are handled.
