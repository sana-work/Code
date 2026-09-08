# VEGA Asset Services Single-Agent Deployment Checklist

## What the observed trace means

The trace shows this order:

1. `vega_agent` started.
2. `query_as_events_entitlements` completed successfully.
3. `set_model_response` failed.
4. The UI returned `Internal Server Error`.

The Asset Services request and provider call therefore completed. The failure
is at the final structured-response boundary.

## Required configuration change

Do not replace only the Root Orchestrator instruction text. A single-agent
deployment must replace the complete response contract and bypass the old
downstream chain.

| Setting | Old Root Orchestrator | Asset Services single agent |
| --- | --- | --- |
| Response schema title | `OctobotRootHandoffSchema` | `OctobotExecutionSchema` |
| Output key | `root_handoff` | `schema` |
| Business tools | None | `query_as_events_entitlements`, `query_as_cash_entitlements` |
| Output destination | AS specialist, then formatter | Final UI response |

Apply all fields from
`Octobot_Asset_Services_Single_Agent_System_Prompt.yaml` together:

- `instruction`
- `response_type: JSON`
- the complete `output_schema`
- `output_key: schema`

Keep the platform's registered `set_model_response` finalizer, but bind it to
`OctobotExecutionSchema`. Remove or bypass the Root Handoff, AS Specialist, and
Formatter transitions for this single-agent route. Publish a new agent version
and test in a new session so a cached root schema is not reused.

## Smoke tests

Run these in order:

1. `Hi`
   - No Asset Services business tool is called.
   - `set_model_response` succeeds.
   - Final status is `SUCCESS` with empty arrays.
2. `features`
   - No Asset Services business tool is called.
   - The final response contains the capability table and succeeds.
3. A known valid event lookup
   - The Events Entitlements tool succeeds.
   - `set_model_response` succeeds and the table renders.
4. A category-conflict lookup
   - Example intent: request details for a voluntary event whose returned
     category is mandatory.
   - Final status is `NEEDS_CLARIFICATION`.
   - `attributes`, `tables`, and `options` are empty.
   - No `error` property is present and no contradictory record is rendered.

If test 1 fails at `set_model_response`, the deployed response schema or output
key is still incorrect; no provider debugging is needed. If only a data test
fails before `set_model_response`, investigate the relevant business tool.

## Payload checks

For any remaining finalizer failure, capture the rejected finalizer arguments
and validation message. Check specifically that:

- the payload is an object, not a JSON-encoded string;
- all seven required final properties are present;
- `attributes`, `tables`, `options`, and `toolsUsed` are arrays;
- attribute values, table columns, and table cells are strings;
- `error` is omitted for non-failed responses rather than set to `null`;
- the payload is not wrapped under `root_handoff` or another obsolete key.
