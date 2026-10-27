# Universal Chat Prompt Tests

This is a reusable, synthetic-only test bench for the Universal Chat / VEGA / Octobot single-agent prompt. It cannot connect to banking systems or send client emails. All references, counterparties, amounts, and records are invented.

## Current Contract: 27 October 2026

AS now returns no default output columns, and evidence tables have no numeric column cap. `field_selection_policy.py` and `test_field_selection_policy.py` add 47 reference-policy/static checks for explicit AS field plans, unchanged input filters and TM defaults, requested/decisive column coverage beyond six columns, full-table fidelity, ten-row suppression, cache-versus-new-field behavior, and unchanged date/UI contracts. Together with the earlier 54 unit tests, 101 checks pass. These checks exercise deterministic reference logic and prompt invariants, not a live language model or response-time benchmark.

The subsequent final-delivery follow-up adds 35 checks in `test_final_delivery_policy.py`, for 136 local tests in total. They cover string-only error initialization, transport/direct-delivery instructions, finalizer exclusion from toolsUsed, source literal-null preservation and unchanged business/date/UI contracts. The UI schema still permits an omitted error, but the revised prompt always supplies its string value. These are not live-model finalization or runtime event-deduplication tests. Versioned snapshots/results are under `reports/2026-10-27/finalization-followup/`; earlier reports remain historical.

The rest of this README describes the historical model-trial harness. Its dispatcher still adds AS defaults and its grader enforces the earlier six-column limit; it must not be used unchanged to evaluate the current prompt. The old 50-case scores, traces and snapshots remain historical. No current production tool schema or native deployment-model evaluation is asserted. The new versioned report is under `reports/2026-10-27/`.

## Results And Scope

Start with `reports/TEST_FINDINGS.md` and `reports/evaluation.md`. The tested prompt is frozen in `reports/prompt_snapshot.yaml`; its original UI schema is retained. Each file in `reports/live/` records actual mock-tool calls, returned evidence, and the live testing agent's first final response.

Three live Codex testing agents made the decisions about tools, arguments, evidence mode, selected columns, and wording. They used a local dispatcher instead of native banking tools. Exact array copying/projection was code-assisted. These trials therefore test instruction application with a tool-capable actor, not unaided token-by-token table copying by the deployed model. Testing agents were instructed not to read private expectations; this is procedural isolation, not a filesystem security boundary.

The target production model, native tool bindings, caller authentication, and UI renderer were not exercised. A Responses API adapter is supplied, but no real API model run was performed for the bundled results. Passing these finite cases does not prove the prompt can never hallucinate or fail.

## Setup

Use Python 3.10 or later in this folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

## Replay And Inspect

```sh
.venv/bin/python harness.py list
.venv/bin/python harness.py context --case as_cash_paid
.venv/bin/python harness.py grade --out reports/evaluation.json
```

Grading rechecks saved observations; it does not generate fresh model answers. Missing cases are `NOT_RUN`, never passes. The report checks the original UI structure plus stricter prompt requirements: one final object, actual tool usage, parallel dispatch, exact identifiers, decisive requested fields, selected facts, supported formatting, six-column compact evidence, ten-row suppression, and full source-table equality.

`fixtures.py` contains the synthetic schemas, evidence, and private expectations. A different deployed schema may use different fields or business meanings. Substitute its approved descriptions and fabricated records before claiming production compatibility. The mock dispatcher supports the finite exact-filter scenarios in this suite; it is not a complete custody search engine or calendar implementation.

## Run A Testing Agent Locally

Use `TEST_AGENT.md` as the actor protocol. Supply only the output of `context` to the actor, not `fixtures.py`, grader code, or previous scores. Use a fresh run directory for every experiment:

```sh
.venv/bin/python harness.py --run-dir reports/new-trial context --case as_cash_paid
.venv/bin/python harness.py --run-dir reports/new-trial dispatch --case as_cash_paid --request-file requests.json
.venv/bin/python harness.py --run-dir reports/new-trial submit --case as_cash_paid --response-file response.json
.venv/bin/python harness.py --run-dir reports/new-trial grade --out reports/new-trial-evaluation.json
```

The actor must produce `requests.json` as an array, for example:

```json
[{"name":"query_as_events_entitlements","arguments":{"event_id":"0001000001","account_id":"00123456","limit":50,"offset":0}}]
```

`response.json` is the actor's one final UI object. Do not dispatch for no-tool cases. The dispatcher runs multiple calls together, rejects repeated or unapproved tools, and returns optional fields only when requested. It cannot invent a useful result for an unsupported argument. Preserve the first attempt; never replace a failure with a corrected response under the same run.

## Test Your Actual API Model

Configure credentials outside this package. Never put real client data or keys into fixtures or committed files. API calls can incur model charges. Select the same model used by your application; no model is guessed by this harness.

```sh
export OPENAI_API_KEY='<your test key>'
export OPENAI_MODEL='<your deployed model id>'
.venv/bin/python harness.py --run-dir reports/api-trial run-api
.venv/bin/python harness.py --run-dir reports/api-trial grade --out reports/api-trial-evaluation.json
```

Use `--case CASE_ID` repeatedly after `run-api` to run a subset. Use `--base-url` only for a trusted Responses-compatible endpoint. This adapter sends the tested instruction, original schema, synthetic contexts, and mock results to that endpoint. It uses JSON mode and separately validates the original schema, rather than altering your UI contract to fit strict structured-output restrictions.

To test a revised YAML, pass `--prompt /absolute/path/to/revised.yaml` before the command and use a new run directory. Preserve the tested file and a run manifest. Repeat evaluations across multiple runs and inspect factual grounding, not only the aggregate pass rate.

## What To Add Before Release

- Exact deployed tool schemas and their returned column descriptions, using synthetic evidence only.
- Native-agent tests with the production model and runtime's actual final-delivery configuration.
- UI checks for full tables containing literal markup, Unicode, quotes, blanks, commas, and line breaks. The renderer must treat cells as data and never execute source markup.
- Further tests for week/month conventions, daylight-saving transitions, unknown pagination metadata, unsupported filter combinations, grounded clarification choices, conflicting context, and dependent multi-step enquiries.
- Repeated runs, adversarial variations, and human review of client email quality and every operational conclusion.

## Zero-Time Date Display Follow-Up

The current prompt now has a narrow display-only exception: valid registered date/date-time values at exactly zero time display as `YYYY-MM-DD`, including compact and full tables. Raw evidence and non-zero times remain unchanged. `test_zero_time_date_display.py` supplies 30 reference-policy/schema checks; together with the original evaluator tests, 54 unit tests pass. These are not new live model trials.

The original 50-case results, prompt snapshot, traces and run manifest remain historical and unchanged. The general harness grades their original exact-cell policy; its current table comparator does not implement the newer date-display exception. A fresh model evaluation containing zero-time date cells must use a date-aware expected presentation, rather than incorrectly treating the authorized formatting as source corruption. Do not present the earlier 47/50 result as validation of this follow-up change.
