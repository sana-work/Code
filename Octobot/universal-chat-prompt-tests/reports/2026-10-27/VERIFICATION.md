# AS Output Selection And Column Coverage: Verification

27 October 2026

## Result

101 unit tests passed: the prior 54 checks plus 47 new reference-policy/static checks. `unit_tests.xml` records the run. These are not model-generated trials, a production banking-tool test or an agent-latency measurement.

The new synthetic adapter requires non-empty, exact AS requested_fields and returns no unrequested AS default outputs. Tests cover deduplicated evidence plans, explicit/decisive fields, identifiers and currency, more than six required columns for AS and each TM service, missing evidence, row/header/value fidelity, ten-row suppression, complete table views, date-only presentation and when new fields require another turn's lookup. Field meanings use an invented registry, not a verified production schema.

## Preserved Contracts

- The input identifier/filter section and date/timezone section are unchanged from `baseline_prompt.yaml`.
- The UI schema string, response_type and output_key are unchanged. Schema SHA-256: `c8a46ceac9cc5d2d733778373cec24f4c1cd6a5c2075a6a5a1e7a80f7867a51f`.
- TM default-output behavior, one call per tool, parallel independent calls, ten-row table suppression, full-table override and zero-time date display remain.
- No historical trial, score, trace, dispatcher or grader was rewritten. The historical harness still embodies the earlier AS defaults/six-column contract; use the isolated new policy tests for these changes, not that grader unchanged.

`current_prompt.yaml` freezes the revised YAML. File hashes and size metrics are in `verification.json`. Instructions decreased from 38,952 to 36,413 characters and from 5,577 to 5,145 whitespace-separated words. Those are not token counts, speed measurements or proof of faster responses.

## Remaining UAT Work

The exposed production AS schema must provide current supported output names and exact column meanings without obsolete default-output assumptions. Verify actual requested-field coverage and returned payloads against that binding. Run the real deployment model on client-email variants, multi-part enquiries, wide required evidence, date/null cases, multiple parallel tools and full-table follow-ups.

Measure repeated before/after completed-response times at comparable load, including per-tool overlap and model timings. No measured latency improvement is asserted. Runtime recommendations in Universal_Chat_Latency_Optimization.md are proposals, not implemented backend changes.

The UAT email, release notes and local PNG/SVG/PDF architecture are synchronized with the new policy. The architecture was regenerated and its PDF render visually reviewed; no reference footer was added.
