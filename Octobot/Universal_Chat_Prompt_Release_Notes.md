# Universal Chat / VEGA / Octobot: Prompt Release Notes

Prepared: 14 October 2026

Revised: 27 October 2026

Status: UAT candidate documentation. Deployment and UAT sign-off are not asserted.

## Baseline And Scope

Comparison baseline: the last-running single-agent prompt shown in the 13 October screenshots, including its mandatory full-width tables, retrieval-count messages, TM detail template and reference fallback rules. The older specialist/root-agent screenshots are not the release baseline.

The current YAML is the source of expected behavior for this candidate. This is a prompt-level change, not evidence of new backend fields, expanded source-system coverage, a UI deployment, or new operational capabilities.

## Changes From The Last-Running Prompt

| Area | Last-running behavior in screenshots | Updated expected behavior |
| --- | --- | --- |
| Primary answer | Table-centric presentation; successful data required complete record tables. | A complete, client-friendly answer leads. Tables serve as supporting evidence. |
| AS presentation | Plain narrative with limited emphasis. | Relevant business labels and restrained bold emphasis for decisive facts, dates, amounts and statuses. Irrelevant sections are omitted. |
| Email replies | No dedicated automatic email-recognition/reply template in the shown prompt. | Email-shaped input activates email replies without requiring a subject. Explicit requests to draft/format an email also activate this mode. |
| AS output selection | The AS tool supplied default output columns; additional outputs were additive. | AS has no default outputs. Every AS data call explicitly requests all supported client-requested and decisive fields, identifying fields, currencies and units needed for the answer. Input filters are unchanged. TM retains its registered defaults. |
| Default table width | All authoritative returned columns; TM enforced its complete default display prefix. | No fixed column cap. Every displayed AS/TM table includes all supported requested columns and the returned evidence used to answer, with needed identifiers/currencies/units. Only unrelated columns may be omitted; source order and retained values remain exact. |
| Default table size | Successful record tables were mandatory regardless of display size. | Tables are shown when the combined supporting row count is 1-10. Above ten, all tables are withheld and a single table-view offer is made, unless a required clarification takes precedence. |
| Explicit table request | No distinct full-view mode separate from the mandatory table behavior. | An initial table request or acceptance of an offer displays every column and row of the applicable returned tables, overriding ten-row suppression. The only permitted displayed-value change is the zero-time date formatting described below. |
| Zero-time date display | Midnight date-time strings were retained in narrative and tables. | Registered date/date-time fields with time exactly zero are displayed as `YYYY-MM-DD` in chat, email, attributes and all table modes. Non-zero time components remain unchanged. |
| Table-only follow-up | Prior results could not serve as current-turn evidence for new data requests. | Complete validated prior results may be re-presented for a table-only follow-up without claiming freshness. If unavailable, uniquely identified prior criteria may be queried again. New data questions still require fresh evidence. |
| Response order | The single-record TM template placed the table before its detail block. | Full summary, relevant detail blocks, limitations and email closing precede the titled evidence appendix. No narrative follows the final table. |
| TM detail structure | Fixed three-label detail blocks for a single result; listings used table/count presentation. | The three business labels remain. Single-result details and multi-result summaries come before evidence; differences across results must be explained rather than assumed away. |
| Lookup announcements | Required "Showing X matching record(s) on this page (Max 50)" wording and related count statements. | Retrieval counts and paging mechanics stay out of client replies. A requested business count is still answered when the evidence supports it. |
| Generic TM reference | Selected-service, sequential reference fallback; ambiguity could require service clarification. | All applicable TM services accepting the exact reference may be searched together, once each. The reference is not relabelled into another identifier type. |
| Evidence collection | Sequential fallback was an exception to per-tool call limits. | All required independent calls are prepared upfront and dispatched together. Each tool runs at most once per turn, with no retry, extra-field lookup or second-page call. |
| Response efficiency | Repeated planning/checklist wording and broad returned outputs could add work. | Plan the complete evidence set once, request only necessary AS outputs, validate once, and compose one concise final response. No added planner/formatter calls, arbitrary answer-length cap or reduced evidence coverage. Actual latency improvement has not been measured. |
| Action conclusions | The prior Current/EOD template allowed "No further action is required" when fail/market status was null or absent. | Missing fail/market status is unavailable information, not proof that no issue or action exists. Action conclusions require an explicit supported mapping. |
| Coverage and calculations | Page length could be used to describe additional availability or final-page completeness. | Completeness requires valid metadata or a documented short-page rule. Counts, sums and latest timestamps are qualified when coverage is unproven. A full page alone proves neither completeness nor additional matches. |

## Response Structures

**Chat:** Summary and complete business answer; relevant AS labels or TM detail sections; limitations/essential clarification; titled supporting tables when eligible.

**Email:** Supplied subject, if any; greeting; optional acknowledgement; summary and complete business reply; closing; titled supporting tables when eligible. The optional large-result table offer is a separate chat follow-up after the email closing, not part of the client email.

For TM, retain these labels in order: **Parties involved**, **Settlement information**, **Current Status & Action Required**. Keep Current Transactions, dated EOD snapshots and Settlement Instructions distinct. The labels do not authorize unsupported action claims or cross-service field substitution.

## Table Decision Rules

1. An explicit table request, including acceptance of the preceding offer, takes precedence: show complete valid returned tables without column or row selection changes. Only eligible zero-time date display values may be formatted.
2. Otherwise, add up the rows across valid non-empty successful results supporting the reply. For 1-10 rows, display every source row and all requested/decisive evidence columns, including necessary identifying fields, currencies and units. There is no numeric column cap.
3. Above ten rows, display no tables and offer: "Would you like me to show the supporting details in a table?" A required business clarification takes precedence over this presentation question.
4. With no valid supporting rows, create no empty table or table offer. Independently valid portions of a mixed result still follow the applicable rules.

The threshold is a display rule, not a combined business total. A full-table view does not fetch new pages or add optional fields that were not originally returned. An additional-field request is a new evidence lookup, not a cached table view. Each lookup remains limited to one page of at most 50 rows per service per turn; a later "next batch" is a separate lookup.

## Final Delivery Follow-Up: 27 October

- Removed the unconditional ban on set_model_response. When the runtime registers it as the final-response transport, submit one complete validated payload through it, then stop without a second direct answer or completion message. When it is not registered, return one direct JSON object. The finalizer is separate from business-tool calls and toolsUsed.
- Every final payload now explicitly includes error as a string: exactly "" for SUCCESS, NEEDS_CLARIFICATION and OUT_OF_SCOPE; a safe non-empty code/message for FAILED. JSON null is prohibited. The existing UI schema already permits this property; its text, types, required list, response_type and output_key are unchanged.
- Validate before submission rather than probing the finalizer. Output serialization correction must not repeat completed AS/TM lookups.
- This is prompt-only hardening. It does not implement runtime event deduplication, confirm why the observed second finalizer call occurred, or guarantee that the publisher cannot emit duplicate final events.

## Retained Or Clarified Safeguards

- Single-agent operation and the existing final UI field names, types and table-placeholder contract are unchanged. One final response is expected; runtime duplication must still be checked in UAT.
- AS and TM remain read-only lookup domains. No email sending, payment processing, settlement action, escalation or SWIFT generation is introduced.
- Registered tool parameters and column descriptions determine supported fields, filters and meanings. AS requested_fields is non-empty and explicitly covers the complete required evidence set; filters do not imply returned columns. TM mandatory retrieval defaults remain unchanged. Display selection cannot omit a returned client-requested or decisive evidence field.
- Identifiers, leading zeroes, dates, amounts, currencies and source statuses remain exact. Invalid AS account values require clarification rather than silent repair.
- Nulls, blanks, commas, quotes, newlines and unexpected strings are preserved in retained table cells. A genuine source value is not silently cleaned. Distinguish a source-data issue from a model-generated or shifted cell value when reporting defects.
- The sole display-value exception is a valid registered date/date-time with time exactly `00:00:00` and any fractional seconds all zero: display its original `YYYY-MM-DD` date only. Examples with a space, `T`, or no date/time separator are eligible. A valid timezone suffix is removed from that date-only display without converting the date; relevant timezone context remains in prose. Non-zero times, free text, identifiers, blanks and invalid dates are not reformatted. Raw values and cached source tables stay unchanged for lookups and comparisons.
- Missing decisive values cannot become zero, false, "unpaid" or "no action required". Cash, tax, share delivery, event status and payment status must not be substituted for one another.
- Relative dates use the current supplied `userIsoTimestamp` and offset. AS values remain UTC; explicit dates and TM date meanings retain their registered interpretation.
- Existing MT566 timing support remains subject to its registered field meaning. It does not establish an MT564 generation/dispatch time. Key Date, CAID, VOLU/CHOS and other business terms require explicit registered mappings; this release does not add missing mappings or fields.
- No-match outcomes are not lookup failures. One failed service must not discard an independently completed result. Clarifications, unavailable fields and errors must be stated safely.
- Custom HTML, colours, fonts and decorative layouts remain unsupported. Approved bold labels, restrained fact emphasis, email structure and structured evidence tables are supported.

## UAT Coverage

Test plain AS questions, Current/EOD/Settlement Instruction questions, generic TM references, mixed-domain and multi-part enquiries, pasted emails without subjects, and explicit email-drafting requests. Use supported UAT fields and identifiers.

Verify exactly ten versus eleven supporting rows, mixed-service totals crossing ten, explicit initial full-table requests, accepted table offers, cache-present/cache-missing full views, and subsequent page requests. Test default evidence tables needing more than six columns, full views longer than ten rows, narrow AS projections and requests for previously unfetched columns. Verify AS does not rely on implicit identifier, amount, date or status outputs.

Check null, blank, zero, leading-zero identifiers and special-character fidelity; payment date versus payment confirmation; distinct TM statuses; unsupported facts; invalid inputs; partial outcomes; timeout handling; and local-date comparisons. Confirm summary-first/evidence-last order and one final UI response.

Also check `2026-01-01 00:00:00.000`, `2026-01-01T00:00:00.000Z`, and `2026-01-0100:00:00.000` display as `2026-01-01` in prose and compact/full tables. Values such as `2026-01-01T12:30:00.000Z` or `2026-01-01T00:00:00.001Z` must retain their times. No date-looking text in an identifier or narrative cell should be altered.

## Validation Status And Open Items

- Historical synthetic evaluation: 50 first-attempt scenarios; 47 passed and three presentation-wording checks were flagged. There were two confirmed table-position wording violations and one conservative "provided below" flag. Their table data was correct. The latest prompt explicitly prohibits that wording; the original recorded outputs and scores are unchanged.
- That 50-case evaluation predates the zero-time date-display addition and the 27 October AS output-selection/column-coverage changes. Its original prompt snapshot and observations remain unchanged; it is not a fresh model evaluation of these follow-ups.
- Evaluator tests: 24 passed. The synthetic checks include exact full-table equality and compact-table source projections.
- Date-display follow-up: 30 additional reference-policy/schema checks passed, for 54 unit tests in total. These checks cover zero-time variants, non-zero fractional seconds, invalid dates, source preservation and unchanged UI schema; they are not a fresh deployed-model or UI test.
- The 27 October changes add 47 no-default-AS, uncapped-column and contract-preservation reference/static checks. All 101 unit tests pass; results are recorded under universal-chat-prompt-tests/reports/2026-10-27. These are not fresh language-model trials. The historical dispatcher/grader retains its original defaults and six-column contract and must not be used to validate the new contract unchanged.
- The final-delivery follow-up adds 35 payload/schema and static prompt checks, for 136 passing local tests. These check error encoding, delivery-mode instructions and preservation of existing rules, not actual model compliance or executor publication behavior. Its snapshots and results are separate under reports/2026-10-27/finalization-followup.
- Prompt edits target unnecessary work and payload size, not a guaranteed speed increase. No production latency benchmark, deployment-model change, timeout change or runtime concurrency change has been made. See Universal_Chat_Latency_Optimization.md for measurement and implementation recommendations.
- These were tool-capable Codex trials with fabricated results and code-assisted array copying, not the deployed banking model/runtime. Production tool schemas, authentication, UI rendering, default date-window execution and repeated-run behavior still need native UAT validation.
- Verify the deployed Settlement Instructions date-field description consistently defines its intended settlement-date equivalent. The synthetic fixture wording was vague; this is not evidence of a deployed mapping defect.
- No release version number, deployment date, backend change or UAT approval is assumed in these notes.
