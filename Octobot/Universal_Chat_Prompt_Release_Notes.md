# Universal Chat / VEGA / Octobot: Prompt Release Notes

Prepared: 14 October 2026

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
| Default table width | All authoritative returned columns; TM enforced its complete default display prefix. | At most six query-relevant columns per automatically displayed AS/TM table, preserving source order and exact retained values. Retrieval defaults are not reduced. |
| Default table size | Successful record tables were mandatory regardless of display size. | Tables are shown when the combined supporting row count is 1-10. Above ten, all tables are withheld and a single table-view offer is made, unless a required clarification takes precedence. |
| Explicit table request | No distinct full-view mode separate from the mandatory table behavior. | An initial table request or acceptance of an offer displays every column and row of the applicable returned tables unchanged, overriding both display caps. |
| Table-only follow-up | Prior results could not serve as current-turn evidence for new data requests. | Complete validated prior results may be re-presented for a table-only follow-up without claiming freshness. If unavailable, uniquely identified prior criteria may be queried again. New data questions still require fresh evidence. |
| Response order | The single-record TM template placed the table before its detail block. | Full summary, relevant detail blocks, limitations and email closing precede the titled evidence appendix. No narrative follows the final table. |
| TM detail structure | Fixed three-label detail blocks for a single result; listings used table/count presentation. | The three business labels remain. Single-result details and multi-result summaries come before evidence; differences across results must be explained rather than assumed away. |
| Lookup announcements | Required "Showing X matching record(s) on this page (Max 50)" wording and related count statements. | Retrieval counts and paging mechanics stay out of client replies. A requested business count is still answered when the evidence supports it. |
| Generic TM reference | Selected-service, sequential reference fallback; ambiguity could require service clarification. | All applicable TM services accepting the exact reference may be searched together, once each. The reference is not relabelled into another identifier type. |
| Evidence collection | Sequential fallback was an exception to per-tool call limits. | All required independent calls are prepared upfront and dispatched together. Each tool runs at most once per turn, with no retry, extra-field lookup or second-page call. |
| Action conclusions | The prior Current/EOD template allowed "No further action is required" when fail/market status was null or absent. | Missing fail/market status is unavailable information, not proof that no issue or action exists. Action conclusions require an explicit supported mapping. |
| Coverage and calculations | Page length could be used to describe additional availability or final-page completeness. | Completeness requires valid metadata or a documented short-page rule. Counts, sums and latest timestamps are qualified when coverage is unproven. A full page alone proves neither completeness nor additional matches. |

## Response Structures

**Chat:** Summary and complete business answer; relevant AS labels or TM detail sections; limitations/essential clarification; titled supporting tables when eligible.

**Email:** Supplied subject, if any; greeting; optional acknowledgement; summary and complete business reply; closing; titled supporting tables when eligible. The optional large-result table offer is a separate chat follow-up after the email closing, not part of the client email.

For TM, retain these labels in order: **Parties involved**, **Settlement information**, **Current Status & Action Required**. Keep Current Transactions, dated EOD snapshots and Settlement Instructions distinct. The labels do not authorize unsupported action claims or cross-service field substitution.

## Table Decision Rules

1. An explicit table request, including acceptance of the preceding offer, takes precedence: show complete valid returned tables without column or row edits.
2. Otherwise, add up the rows across valid non-empty successful results supporting the reply. For 1-10 rows, display every source row with at most six relevant columns per table.
3. Above ten rows, display no tables and offer: "Would you like me to show the supporting details in a table?" A required business clarification takes precedence over this presentation question.
4. With no valid supporting rows, create no empty table or table offer. Independently valid portions of a mixed result still follow the applicable rules.

The threshold is a display rule, not a combined business total. A full-table view does not fetch new pages or add optional fields that were not originally returned. Each lookup remains limited to one page of at most 50 rows per service per turn; a later "next batch" is a separate lookup.

## Retained Or Clarified Safeguards

- Single-agent operation and the existing final UI field names, types and table-placeholder contract are unchanged. One final response is expected; runtime duplication must still be checked in UAT.
- AS and TM remain read-only lookup domains. No email sending, payment processing, settlement action, escalation or SWIFT generation is introduced.
- Registered tool parameters and column descriptions determine supported fields, filters and meanings. More fields may be retrieved than displayed; display selection does not change mandatory retrieval defaults.
- Identifiers, leading zeroes, dates, amounts, currencies and source statuses remain exact. Invalid AS account values require clarification rather than silent repair.
- Nulls, blanks, commas, quotes, newlines and unexpected strings are preserved in retained table cells. A genuine source value is not silently cleaned. Distinguish a source-data issue from a model-generated or shifted cell value when reporting defects.
- Missing decisive values cannot become zero, false, "unpaid" or "no action required". Cash, tax, share delivery, event status and payment status must not be substituted for one another.
- Relative dates use the current supplied `userIsoTimestamp` and offset. AS values remain UTC; explicit dates and TM date meanings retain their registered interpretation.
- Existing MT566 timing support remains subject to its registered field meaning. It does not establish an MT564 generation/dispatch time. Key Date, CAID, VOLU/CHOS and other business terms require explicit registered mappings; this release does not add missing mappings or fields.
- No-match outcomes are not lookup failures. One failed service must not discard an independently completed result. Clarifications, unavailable fields and errors must be stated safely.
- Custom HTML, colours, fonts and decorative layouts remain unsupported. Approved bold labels, restrained fact emphasis, email structure and structured evidence tables are supported.

## UAT Coverage

Test plain AS questions, Current/EOD/Settlement Instruction questions, generic TM references, mixed-domain and multi-part enquiries, pasted emails without subjects, and explicit email-drafting requests. Use supported UAT fields and identifiers.

Verify exactly ten versus eleven supporting rows, mixed-service totals crossing ten, explicit initial full-table requests, accepted table offers, cache-present/cache-missing full views, and subsequent page requests. Test full views wider than six columns and longer than ten rows.

Check null, blank, zero, leading-zero identifiers and special-character fidelity; payment date versus payment confirmation; distinct TM statuses; unsupported facts; invalid inputs; partial outcomes; timeout handling; and local-date comparisons. Confirm summary-first/evidence-last order and one final UI response.

## Validation Status And Open Items

- Synthetic evaluation: 50 first-attempt scenarios; 47 passed and three presentation-wording checks were flagged. There were two confirmed table-position wording violations and one conservative "provided below" flag. Their table data was correct. These wording issues have not been silently repaired in the prompt or recorded outputs.
- Evaluator tests: 24 passed. The synthetic checks include exact full-table equality and compact-table source projections.
- These were tool-capable Codex trials with fabricated results and code-assisted array copying, not the deployed banking model/runtime. Production tool schemas, authentication, UI rendering, default date-window execution and repeated-run behavior still need native UAT validation.
- Verify the deployed Settlement Instructions date-field description consistently defines its intended settlement-date equivalent. The synthetic fixture wording was vague; this is not evidence of a deployed mapping defect.
- No release version number, deployment date, backend change or UAT approval is assumed in these notes.
