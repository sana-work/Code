# Universal Chat / VEGA / Octobot - Single-Agent Architecture

Prepared: 27 October 2026

## Deliverables

- `Universal_Chat_Single_Agent_Architecture.png`: 3200 x 1600 high-resolution diagram.
- `Universal_Chat_Single_Agent_Architecture.svg`: editable vector diagram with text and shapes.
- `Universal_Chat_Single_Agent_Architecture.pdf`: vector PDF.
- `Universal_Chat_Single_Agent_Architecture.mmd`: Mermaid source for the simpler FigJam architecture overview.
- `layout_validation.json`: label bounds and fit checks.

[Open the editable FigJam overview](https://www.figma.com/board/GDVFQPJJMjYiYLg1ghh9VY?utm_source=chatgpt&utm_content=edit_in_figjam&oai_id=v1%2FDJ4fLiZ1MKYwLeo3vOZQJY4jtrzQIYn7Ic00EUdO4DANuvkfFDfZP5&request_id=e3ee7c6d-227e-4cf2-b0f9-0ec5c565b0df&architecture=true)

The PNG/SVG/PDF diagram includes detailed tool names, network boundaries and response controls. The FigJam overview is a simpler connected-services view, not a pixel-identical copy.

## Architecture

1. One end-to-end Universal Chat agent handles the enquiry. VEGA and Octobot are aliases, not other agents.
2. There are no AS/TM specialist agents or separate formatter agent. The single agent interprets intent, validates identifiers/dates, plans evidence, selects tools and composes the final response.
3. One MCP tool server exposes four registered functions: `query_as_events_entitlements`, `query_tm_current_transactions`, `query_tm_eod_transactions` and `query_tm_settlement_instructions`. There is no separate AS cash-entitlements tool. AS returns no default output columns: every required field must be explicitly requested. AS input filters and TM output defaults remain unchanged.
4. Independent required calls run together; each tool is called at most once per turn. Generic TM references may require all three applicable TM services. AS/TM domains remain distinct.
5. The agent makes no automatic retries or second-page requests. Each selected tool returns at most 50 rows for the turn. This policy does not assert a change to transport-layer retry implementation.
6. The full client summary/email and relevant AS/TM sections precede titled supporting evidence.
7. By default, 1-10 supporting rows across the reply produce tables with all requested/decisive evidence columns and required identifiers, currencies and units. There is no fixed column cap. More than ten rows suppress all tables and prompt one table-view offer, unless an essential business clarification takes precedence.
8. An explicit table request or acceptance of an offer displays all returned columns and rows, overriding ten-row suppression. It does not fetch unfetched pages or invent additional fields.
9. Registered date/date-time values at exactly zero time display as `YYYY-MM-DD`; non-zero times stay unchanged. This is the sole permitted display-value exception. Raw source values, cached results, other cells and the UI contract remain intact.
10. The agent supplies one final JSON payload using the existing `status`, `intent`, `answer`, `attributes`, `tables`, `options`, `toolsUsed` and `error` fields. `error` is `""` for non-failed outcomes or a safe non-empty string for `FAILED`. Use the runtime-registered `set_model_response` transport once when present; otherwise return the object directly once, never both. Finalization is separate from business calls. The UI schema is unchanged; runtime duplicate-publication protection is not implemented by these prompt instructions.

## Scope

- The Citi network contains Live VEGA Chat, Chat BFF, the single-agent runtime, MCP tools, R2D2, enterprise API access and platform data/support services. Vertex AI is shown in the external cloud.
- This is a logical architecture, not a deployment attestation or a code-level network/security review.
- The model is approved and deployment-configured; the diagram does not prescribe a specific model version.
- PostgreSQL and platform support services are shown without specifying a metadata database, guaranteed table-cache persistence or an artifact pipeline.
- The response/safety panel describes prompt rules. The UI remains responsible for rendering the existing structured response; cells must be treated as data rather than executable markup.
- Cached complete results may support table-only follow-ups when available; a new current-status question requires a fresh lookup.


