# GitHub Copilot Prompt: Build the TM Current Securities Transactions MCP Tool

Use this prompt with GitHub Copilot Coding Agent from the root of the Octobot MCP repository. Attach or place the original TM Excel workbook where Copilot can read it, then replace `<WORKBOOK_PATH>` below with its repository-relative or absolute path.

Do not implement from screenshots alone. The original `.xlsx` workbook, including both the `SERVICE` and `DICTIONARIES` tabs, is required as the authoritative TM source. Screenshots are only a visual cross-check.

---

## Role

Act as a senior Python engineer working in the existing Octobot MCP repository. Inspect the repository before changing it, then implement and verify one new Transaction Management MCP tool by following the current checked-in Asset Services implementation pattern.

Do not return only a plan. After repository discovery and workbook validation, make the code and test changes, run the repository's real verification commands, and report the result. Stop only when one of the explicit stop conditions below applies.

## Objective

Implement exactly this new MCP tool:

`query_tm_current_transactions`

Business service: **Current Securities Transactions**  
Domain: **Transaction Management**

This task covers only Current Securities Transactions. Do not implement either of the other TM tools in this change:

- `query_tm_eod_transactions`
- `query_tm_settlement_instructions`

The new tool must use the same architectural approach as the existing Asset Services tools:

- an explicit, agent-visible, typed MCP function signature;
- one immutable, code-defined service contract containing the verified provider mapping;
- a thin tool wrapper;
- the existing shared request validator, provider request builder, provider client, timeout/retry behavior, result normalizer, and logging protections;
- no runtime Excel, metadata database, or generic query-tool dependency.

The currently registered two Asset Services tools must continue to behave exactly as they do today. After this change, the expected MCP inventory is the existing two AS tools plus this one TM tool, for a total of three tools, unless repository inspection proves that the intentional current inventory is different. Report any such difference before editing.

## Required Inputs

1. Repository root: the current working directory.
2. TM workbook: `<WORKBOOK_PATH>`.
3. Existing Asset Services implementation and tests in the repository.
4. Any checked-in architecture document is context only. Current code, tests, and the original workbook are authoritative for this task.

## Known Workbook Cross-Checks

Use the following values only to verify that the correct workbook and service were supplied. Do not substitute them for reading the workbook.

Expected `SERVICE` row:

| Field | Expected value |
|---|---|
| Portable Id | `fdbc0b64-8bb3-46e2-b4fa-dccccd4cc377` |
| Name | `TCD2_JOINS_IOD` |
| English Name | `Current Securities Transactions` |
| Type | `database` |
| Data Entitlement Model Type | `CDS` |
| Account Types | `S/K` |

The visible description begins with `Current Securities Transactions provides recent security transactions activity for each ...`; read the complete cell from the workbook.

Expected `DICTIONARIES` identity values:

- Catalog: `CDS2_RT`
- Service: `TCD2_JOINS_IOD`
- Portable Id: `fdbc0b64-8bb3-46e2-b4fa-dccccd4cc377`

The screenshots showed these dictionary headers, but the workbook must be checked for all headers and any additional columns:

1. `Catalog`
2. `Service`
3. `Portable Id`
4. `Original Column Name`
5. `English Column Name`
6. `Column Description`
7. `Data Type`
8. `Column Order`
9. `Is Trusted`
10. `Is Default Output`
11. `Is Critical Data Element`
12. `Critical Data Element Category`
13. `Is Grain`
14. `Grain Type`
15. `Is Key`
16. `Sort Order`
17. `Is Output Column`
18. `Is Calculated Column`
19. `Is Client Code Column`
20. `Is Parameter`
21. `Is Range`
22. `Is Required Filter`
23. `Filter Group Number`
24. `Partition Key Index`
25. `Is Partitioning Field`
26. `Expression`

Visible sample provider columns included `ACCT_BASE_NBR`, `ACCT_BUS_ID`, `ACCT_BUS_TYP_CD`, `ACCT_GEN_ID`, `ACCT_ID`, `ACCT_MNEM`, `ACCT_NME`, `ACCT_TITLE`, `ACQ_DISP`, `ACRL_BASIS_CDE`, `ACRL_BASIS_NME`, `ACT_SETT_DT`, `ACTVY_TYP_SEQ`, `ALT_ACCT_NME`, `ALTV_CUR_CD`, `AMORT_QTY`, `AVAL_BAL_ASOF_DT`, `BASE_UNIT_PRC_AMT`, `BKING_CUR_CD`, `BLK_POOL_ID`, `BR_ID`, `BR_NME`, `BRKR_ORDER_ID`, `BRKR_REF_NO_DESC`, `CALLABLE`, `CLCL_BRKR_COMM_AMT`, and `CLEARING_AGENT`. These are incomplete examples, not the allowed contract.

## Source Precedence

Resolve facts in this order:

1. Current repository behavior and tests for shared mechanics.
2. The complete original TM workbook for this service's identity, fields, types, descriptions, output flags, and filter flags.
3. Existing verified provider or non-production evidence already checked into the repository.
4. Current architecture documentation.
5. Screenshots, only as cross-checks.

Never invent a portable ID, provider column, business field name, output field, required filter, optional filter, alias, enum value, date format, range rule, filter group rule, default output, response key, pagination rule, or provider operator.

If two authoritative sources conflict, stop and report the exact conflict with workbook sheet/row/cell references and code locations.

## Phase 1: Inspect the Repository Before Editing

Locate and read the actual current equivalents of the following. Do not assume these paths still exist or blindly copy old documentation paths:

- `ServiceToolContract`, `FieldContract`, and `ValueType`;
- Asset Services contracts and business-to-provider output mappings;
- the two Asset Services MCP wrappers and their generated schemas;
- the shared service-tool runtime;
- provider request and filter models;
- provider service/client, authentication, deadline, retry, and `Retry-After` handling;
- correlation/request-context handling;
- logging filters and sensitive-data redaction;
- server composition and tool registration;
- exact tool-inventory tests;
- contract, schema, runtime, provider-request, timeout, and error tests;
- environment YAML/configuration loading;
- the repository's documented test, lint, and CI commands.

Before changing code, summarize in the task log:

- the current tool inventory;
- the exact files/classes/functions that form the AS reference path;
- which modules can be reused unchanged;
- which files need a narrowly scoped TM addition;
- any uncommitted changes already present, so they are preserved.

Do not replace existing user changes or perform unrelated cleanup.

## Phase 2: Audit Both Workbook Tabs

Read `<WORKBOOK_PATH>` with a structured Excel reader, preferably `openpyxl` in read-only/data-only modes as appropriate. Do not use OCR, screenshot transcription, CSV conversion, or ad hoc text parsing as the contract source.

Inspect the workbook completely:

1. List all sheet names and identify `SERVICE` and `DICTIONARIES` case-sensitively.
2. Record used dimensions, tables, hidden rows, hidden columns, filters, merged cells, formulas, and blank trailing ranges that affect interpretation.
3. Read every header exactly as stored.
4. Read the complete `SERVICE` row, including cells clipped in screenshots.
5. Read every populated row in `DICTIONARIES`, not only the first visible page.
6. Confirm that every dictionary row belongs to `TCD2_JOINS_IOD` and uses the expected portable ID.
7. Calculate and report the workbook SHA-256 hash for traceability.
8. Do not add the workbook to Git unless repository policy explicitly requires and permits it.

Produce a temporary audit table with one entry per dictionary row containing:

- Excel row number;
- original provider column;
- English column name;
- full description;
- data type;
- column order;
- every boolean/capability flag;
- filter group number;
- partition metadata;
- expression text, if present;
- proposed explicit business key;
- interpretation notes or unresolved ambiguity.

Also report:

- total populated dictionary rows;
- duplicate provider columns;
- duplicate English names;
- proposed business-key collisions;
- blank required cells;
- every distinct `Data Type` value;
- every distinct raw boolean representation;
- counts and row lists for `Is Output Column`, `Is Default Output`, `Is Parameter`, `Is Required Filter`, `Is Range`, `Is Calculated Column`, `Is Key`, and non-empty `Filter Group Number`;
- contradictions such as default output without output capability, required filter without parameter capability, or duplicate column orders.

Do not edit implementation files until this audit passes.

## Workbook Interpretation Rules

Apply these rules conservatively and record the source row for every resulting contract entry:

- `Original Column Name` is the exact internal provider column. Preserve case and spelling.
- `English Column Name` and `Column Description` are the business-language source, not automatically generated Python identifiers.
- Define each public business key explicitly in checked-in code using reviewed `snake_case`. Do not derive public keys mechanically at runtime.
- `Is Output Column = TRUE` is required for a field to be selectable or returned.
- `Is Default Output = TRUE` makes a field a default only when `Is Output Column = TRUE` as well. Treat any contradiction as a workbook defect and stop.
- `Is Required Filter = TRUE` normally means an explicit required MCP parameter, but validate its relationship with `Is Parameter` against the workbook and the existing AS contract semantics.
- `Is Parameter = TRUE` is only evidence that a field may be filterable. Confirm the repository's existing interpretation before using it.
- Do not expose a filter merely because a field is an output column.
- Do not expose an output merely because a field is a filter parameter.
- Current shared runtime behavior is equality filtering unless the code and provider contract prove otherwise.
- If any required field has `Is Range = TRUE`, belongs to a filter group, or requires non-equality/list/OR semantics, do not approximate it as equality. Stop and report the missing semantics unless the existing repository has a verified implementation that can be reused.
- Never execute, compile, evaluate, or expose text in the `Expression` column. If calculated columns are legitimate selectable outputs, pass only the verified provider column through the existing provider API and document how the provider owns the calculation.
- Map workbook data types through the existing `ValueType` model. If a required type is unsupported, make the smallest explicit shared extension with focused tests, or stop if provider serialization semantics are unknown.
- Preserve identifiers as strings when their business meaning or source contract requires preserving leading zeroes.
- Do not infer that `ACCT_ID`, `ACCT_BASE_NBR`, `ACCT_BUS_ID`, or any similarly named account column is the approved Safe Account/Security Account filter. Use only explicit workbook flags plus verified business/provider evidence.
- Do not carry AS aliases into TM automatically. Any TM alias, including Safe Account terminology, must be directly supported and unambiguous for this service.
- Do not expose provider columns, portable IDs, catalog names, service codes, provider routes, credentials, raw filters, expressions, or authentication data in the MCP schema or tool description.

## Implementation Requirements

### 1. TM contract

Follow the current repository organization. If it matches the AS layout, add a focused Transaction Management contract module such as `octobot_mcp/contracts/transaction_management.py`; otherwise use the established equivalent location.

Define one immutable `ServiceToolContract` for `query_tm_current_transactions` containing only workbook-verified data:

- domain `TRANSACTION_MANAGEMENT`, following the repository's exact domain convention;
- expected portable ID;
- explicit business-key to `FieldContract` mapping;
- exact provider columns;
- value types;
- required/filterable/selectable capabilities;
- explicit aliases only when verified;
- default output fields derived from valid workbook flags;
- the existing agent result limit cap unless a different TM cap is explicitly verified.

The TM contract module must be the single authoritative source for both input and output mappings for this service. Do not generate or add a second field-mapping document/module that can drift from it.

Run the same contract self-validation used by AS, including at least:

- unique business keys and normalized aliases;
- unique provider columns where required by current rules;
- every default output is selectable;
- every required input is filterable;
- non-empty valid portable ID;
- supported value types;
- valid pagination cap.

### 2. Agent-visible output selector

Create an enum, `Literal`, or the repository's established equivalent containing exactly the selectable TM business keys. Use it for `requested_fields` so the generated MCP JSON schema exposes an allowlist.

Do not expose workbook/provider names in this enum. Do not allow arbitrary strings.

### 3. Explicit MCP wrapper

Add one tool wrapper following the current AS class/module pattern. If appropriate, use a focused module such as `octobot_mcp/tools/transaction_management_tools.py`.

The public function must be named exactly:

`query_tm_current_transactions`

Requirements:

- tag it using the repository's Transaction Management tag convention;
- use a concise business description explaining when an agent should select it;
- expose every verified required filter as a required named parameter;
- expose every verified optional filter as an optional named parameter;
- use precise Python/Pydantic types and constraints supported by the workbook/provider contract;
- expose `requested_fields` as the verified output allowlist;
- expose the existing standard `limit` and `offset` controls with the shared cap/defaults;
- obtain the correlation ID from the existing request context/auth middleware, never from an agent-supplied `request_id` parameter;
- build only a business-key/value mapping and delegate to the existing shared execution function;
- do not use `**kwargs`, a generic filter dictionary, raw filter expressions, provider columns, a portable ID argument, a provider URL argument, or authentication arguments;
- do not duplicate validation, HTTP, retries, timeouts, normalization, or logging logic in the wrapper.

Descriptions must use approved business wording from the workbook while excluding provider internals and portable IDs.

### 4. Shared execution path

Reuse the current shared path used by AS. Extend shared code only when a verified TM requirement cannot be represented by the existing abstractions.

The complete call must retain these behaviors:

1. Validate contract identity.
2. Validate pagination and required/optional values locally.
3. Reject unknown or invalid inputs before any provider call.
4. Resolve default or requested output fields against the selectable allowlist.
5. Build structured provider filters from verified business keys.
6. Map filters and selected outputs to exact provider columns.
7. Read the portable ID only from the internal contract.
8. Call the provider through the existing shared provider service.
9. Keep retries bounded by the existing total tool deadline.
10. Respect current retry classifications and `Retry-After` handling.
11. Normalize provider rows back to business `snake_case` keys.
12. Return the current JSON-safe structured result contract for MCP consumers.
13. Keep provider response bodies, credentials, internal URLs, query values, stack traces, and sensitive identifiers out of agent-visible errors and non-redacted logs.

Do not add a runtime workbook reader, metadata repository, database lookup, generic query tool, health-check MCP tool, or a second provider client.

### 5. Registration

Register `query_tm_current_transactions` through the existing server composition mechanism.

Update exact-inventory assertions from the two existing AS tools to the intended three-tool set:

- the two existing AS tool names, unchanged;
- `query_tm_current_transactions`.

Do not register the two future TM tools as placeholders. Do not rename the AS tools.

### 6. Scope boundaries

Do not update Root Agent, TM Specialist Agent, Formatter Agent, UI, or final production response prompts in this tool-only task unless those files are already part of MCP tool registration and a minimal change is required to make the tool callable.

Do not change the established UI result contract. The MCP tool should return the same structured service result consumed by the agent layer; the final user experience remains plain text plus tables, not raw JSON/JSONB.

Do not perform unrelated refactors or broad module splitting.

## Required Tests

Follow current test conventions and add focused tests in the corresponding TM or shared test modules.

### Contract and workbook-derived mapping tests

- The tool contract has the exact expected name, domain, and portable ID.
- Every implemented contract field is traceable to one workbook row.
- Every selectable field has `Is Output Column = TRUE`.
- Every default field has both default and output flags set.
- Every required filter is required in the contract and agent schema.
- Every optional filter is optional in the schema.
- Every provider column and data type matches the workbook exactly.
- Business keys and aliases are unique and deterministic.
- Filter-only fields cannot be requested as outputs.
- Output-only fields are not silently accepted as filters.
- Default outputs are valid selectable fields.

### Generated MCP schema tests

- `query_tm_current_transactions` is registered exactly once.
- Its required array is exact.
- Optional fields are present but not required.
- `requested_fields` is a strict allowlist of verified business keys.
- field types, patterns, lengths, numeric constraints, defaults, and descriptions are present where verified;
- provider columns, portable ID, service code, catalog, URL, credentials, raw filter objects, `request_id`, and `**kwargs` are absent;
- the complete registered inventory is exactly the intended three tools.

### Runtime and provider-request tests

- A valid minimal request maps to the exact portable ID, output columns, and filter columns.
- A valid request with selected outputs preserves requested order according to existing runtime rules.
- Omitted `requested_fields` uses the verified defaults.
- Pagination values and cap are enforced.
- Each supported data type is validated and serialized correctly.
- Identifier strings preserve leading zeroes.
- Invalid values fail locally and the provider mock is not called.
- Missing required inputs fail locally and the provider mock is not called.
- Unknown requested output fields fail locally and the provider mock is not called.
- Comma/list/range values are rejected unless their semantics are explicitly verified and implemented.
- Ambiguous account fields are not treated as Safe Account aliases.
- Provider output columns normalize to the explicit TM business keys.
- Unknown or malformed provider fields follow the current safe normalization policy.
- Empty provider results produce the current no-data response.
- Provider 4xx/5xx, connection failure, timeout, and cancellation produce the existing safe error structure.
- Retryable failures use current bounded retry rules; non-retryable failures are not retried.
- Deadline expiry cancels in-flight work and returns the current retryable timeout result.
- logs and agent-visible results do not leak credentials, internal URLs, full query payloads, provider response bodies, or sensitive filter values.

### Regression tests

- All existing AS contract/schema/runtime tests remain unchanged and pass.
- Both AS tools generate the same schemas and provider requests as before.
- No removed generic/discovery/health MCP tool is reintroduced.

## Verification Commands

Discover and run the repository's actual documented commands. At minimum, if still supported, run:

```bash
python -m pytest tests/ -q -p no:cacheprovider
python test_runner.py
ruff check octobot_mcp tests
```

Also run the narrow new TM tests first and inspect the generated MCP tool schema directly. If the repository provides a local MCP development client, use it to:

1. list tools and confirm the exact three-tool inventory;
2. call `query_tm_current_transactions` with a deterministic mocked/non-production-safe request;
3. verify default fields, selected fields, no-data behavior, local validation, and one normalized provider error.

Do not use production credentials or production data for verification.

## Stop Conditions

Stop before implementation, or stop the affected part of implementation, and report exact evidence if any of these occur:

- `<WORKBOOK_PATH>` is missing or is not the original readable `.xlsx` file;
- either `SERVICE` or `DICTIONARIES` is missing;
- workbook identity does not match the expected service or portable ID;
- the dictionary is incomplete, filtered in a way that hides source rows, or contains unresolvable duplicates/collisions;
- a required filter cannot be identified unambiguously;
- account-related fields could map to multiple business concepts without approval evidence;
- required range, grouped, OR, or list-filter behavior is not specified by the provider contract;
- a workbook data type or calculated expression needs unknown serialization/execution behavior;
- code and workbook authoritative facts conflict;
- implementation would require guessing any agent-visible or provider-facing contract value.

When stopped, do not create a plausible approximation. Give a concise blocker table containing the sheet, row/cell, observed value, conflicting evidence, and the exact question the TM/provider owner must answer.

## Definition of Done

This change is complete only when:

- both workbook tabs and every dictionary row were read and audited;
- all implemented TM contract facts are traceable to workbook rows;
- no unresolved ambiguity is needed for the supported tool path;
- `query_tm_current_transactions` has an explicit typed agent schema;
- the tool uses the existing shared runtime and provider service;
- no provider internals are agent-supplied or agent-visible;
- exactly the intended three MCP tools are registered;
- AS behavior is unchanged;
- focused tests, full tests, CI entrypoint, and lint all pass;
- the final report contains no unsupported claim.

## Required Completion Report

At the end, provide:

1. Repository branch/revision and pre-existing working-tree changes preserved.
2. Workbook path, SHA-256, sheet names, SERVICE row identity, and dictionary row count.
3. Screenshot cross-check result for the known values above.
4. Files changed and why.
5. A full contract table with:
   - workbook row;
   - public business key;
   - business label;
   - internal provider column;
   - value type;
   - required;
   - filterable;
   - selectable;
   - default output;
   - aliases;
   - validation constraints.
6. The final generated MCP schema summary, including its exact required fields and output allowlist.
7. The provider-request mapping for one safe example, with sensitive values redacted.
8. Exact registered tool inventory.
9. Tests and verification commands run, with pass/fail counts.
10. `git diff --stat` and any residual risks or unresolved items.

Do not claim completion if the original workbook was not read in full.
