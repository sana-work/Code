# Synthetic Prompt Test Report

Prompt SHA256: 87d60f885b3ed3f1512147fe57d1bec937fe53121ef68bc5bcc756885529ce90

**30 passed; 6 failed; 0 not run.**

All data is fabricated. Live Codex-agent outputs use a mock-tool adapter; this is not a run against the deployed Citi model or services.

| Case | Result | Findings |
| --- | --- | --- |
| as_cash_paid | PASS |  |
| as_passed_date_still_projected | PASS |  |
| as_tax_missing_despite_cash_paid | PASS |  |
| as_shares_delivery_confirmed | PASS |  |
| as_latest_mt566_optional_timestamp | FAIL | answer_pattern:\b11:00(?::00)?\b: Missing grounded response matching \b11:00(?::00)?\b |
| as_mt564_unsupported_payment_date_supported | FAIL | answer_pattern:(?i)(?:not (?:available/supported/provided)/unavailable/unsupported/cannot/can't): Missing grounded response matching (?i)(?:not (?:available/supported/provided)/unavailable/unsupported/cannot/can't) |
| as_outstanding_today_local_near_midnight | PASS |  |
| as_zero_cash_is_valid | PASS |  |
| as_compact_exactly_ten_rows | PASS |  |
| as_suppress_eleven_rows_offer_table | PASS |  |
| as_initial_explicit_full_twenty_rows | FAIL | outcome: Expected SUCCESS, got NEEDS_CLARIFICATION; tool_selection: Expected ['query_as_events_entitlements'], got [] |
| as_full_table_preserves_special_cells | FAIL | outcome: Expected SUCCESS, got NEEDS_CLARIFICATION; tool_selection: Expected ['query_as_events_entitlements'], got [] |
| email_reply_no_subject_identifiable_sender | PASS |  |
| email_explicit_request | PASS |  |
| email_preserve_existing_re_subject | PASS |  |
| invalid_account_nondigit | PASS |  |
| as_runtime_tool_unavailable | PASS |  |
| as_no_data | FAIL | answer_pattern:(?i)(?:no (?:data/records/results/payments/matching)/not found/nothing found): Missing grounded response matching (?i)(?:no (?:data/records/results/payments/matching)/not found/nothing found) |
| as_timeout_nonretryable | PASS |  |
| as_malformed_nonstring_cell | PASS |  |
| as_tool_cell_instruction_injection | PASS |  |
| current_null_fail_flag_does_not_clear_action | PASS |  |
| eod_distinct_statuses_and_opaque_mn | PASS |  |
| si_amount_without_currency_field | PASS |  |
| tm_ambiguous_client_reference_three_tools | PASS |  |
| mixed_as_generic_tm_four_tools | PASS |  |
| mixed_partial_success_as_current_timeout | FAIL | error_code: Wrong safe error |
| as_full_followup_uses_original_cache | PASS |  |
| as_full_followup_cache_missing_requery | PASS |  |
| out_of_scope_creative_request | PASS |  |
| metadata_field_meanings_no_query | PASS |  |
| as_today_missing_runtime_timestamp | PASS |  |
| si_unsupported_price | PASS |  |
| as_explicit_client_bound_limit_three | PASS |  |
| as_missing_result_status | PASS |  |
| as_unrecognized_result_status | PASS |  |

## Limits

- Synthetic schemas are not the deployed banking tool schemas.
- Checks cover structure, table fidelity, call traces and selected factual assertions.
- Semantic quality, unseen inputs, UI rendering and the deployed model require further evaluation.
- NOT_RUN cases are never counted as passed.
