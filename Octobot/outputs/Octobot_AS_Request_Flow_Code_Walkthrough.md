# Octobot Asset Services Request Flow: Code Walkthrough

Date: 2026-09-07

Purpose: explain how one user request moves through the agent prompts, MCP
server, service contracts, provider-query foundation, and final formatter.

## 1. How to use this guide

Read this document in three passes:

1. Read the file map to learn which layer owns each decision.
2. Follow the Events example from the user request to the provider and back.
3. Use the debugging matrix to locate a failure without changing unrelated
   layers.

The file and method names below reflect the latest supplied implementation
reconciliation. Line numbers are intentionally omitted because they change as
the branch evolves. The checked-in MCP code and live registered tool schemas
remain authoritative.

## 2. One-screen mental model

```text
User
  -> Executor
  -> Root Orchestrator prompt
       output: root_handoff
  -> Asset Services Specialist prompt
       calls one or both registered MCP tools
  -> AssetServicesTools typed wrapper
  -> execute_service_tool shared runtime
       reads ServiceToolContract
       validates values and requested outputs
       maps business fields to provider fields
       builds FilterExpression and ProviderQueryRequest
  -> ProviderQueryService
  -> Provider REST API
  <- normalized records or safe error
  <- asset_services_result
  -> Final Response Formatter prompt
       output: schema
  -> Executor JSONB persistence
  -> UI plain text / tables / options
```

The agents know business-facing names. The MCP implementation owns provider
identifiers, provider columns, URLs, credentials, request encoding, and error
normalization.

## 3. File map

### 3.1 Agent prompt files

| File | Reads | Decides | Produces |
|---|---|---|---|
| `Octobot_Root_Orchestrator_System_Prompt.yaml` | User request and safe conversation context | Business route only | `root_handoff` |
| `Octobot_Asset_Services_Specialist_System_Prompt.yaml` | `root_handoff` and registered tool schemas | Events, Cash, both, or clarification | `asset_services_result` |
| `Octobot_Final_Response_Formatter_System_Prompt.yaml` | `root_handoff` plus optional `asset_services_result` | Final status, answer, tables, options | `schema` |

### 3.2 MCP application files

| File | Main symbols or boundary | Responsibility |
|---|---|---|
| `main.py` | Application entry | Start the deployed process |
| `octobot_mcp/server.py` | MCP/HTTP server composition | Connect middleware, readiness, dependencies, and tool registration |
| `octobot_mcp/tools/asset_services_tools.py` | `AssetServicesTools`, `_register_tools`, typed tool wrappers, `_deadline_seconds` | Publish exactly two agent-visible AS tools and delegate execution |
| `octobot_mcp/contracts/common.py` | `ValueType`, `FieldContract`, `ServiceToolContract`, `ServiceToolContract.__post_init__` | Define and validate reusable immutable contract types |
| `octobot_mcp/contracts/asset_services.py` | Events/Cash output maps, output types, contracts, aliases, limits | Own the complete checked-in AS contract |
| `octobot_mcp/runtime/service_tool_runtime.py` | `execute_service_tool`, `_resolve_select_columns`, `_build_filter_expressions`, normalization helpers | Perform shared request validation, mapping, execution, and normalization |
| `octobot_mcp/models/provider_query.py` | `FilterExpression`, `ProviderQueryRequest` | Represent internal provider requests as structured data |
| `octobot_mcp/services/provider_query_service.py` | `ProviderQueryService` and internal filter encoding | Execute provider-neutral HTTP queries and apply transport behavior |
| `octobot_mcp/config/service_schema_registry.py` | Internal schema/configuration lookup | Supply provider-layer service schema information without exposing it to agents |
| `octobot_mcp/config/environment.py` | Typed deployment settings | Load base URL, authentication, timeouts, retry rules, and total deadline |
| `octobot_mcp/utils/request_context.py` | `RequestContext.correlation_id()` | Read the correlation ID created by request middleware |
| `octobot_mcp/utils/time_logger.py` | `time_logger_async` | Record timings without changing business results |
| `octobot_mcp/config/log_filters.py` | Logging filters/redaction | Keep secrets and provider details out of normal logs |
| `dev_client.py` | Manual MCP client | List tools and smoke-test both real tool names against a local server |

The exact HTTP client method inside `ProviderQueryService` may be named
differently as the implementation evolves. The stable boundary is the class:
it receives a structured `ProviderQueryRequest`, calls the provider, and returns
a response or a typed provider failure.

### 3.3 Important deleted duplicates

Do not look for or recreate these as sources of truth:

| Removed artifact | Current replacement |
|---|---|
| `asset_services_output_fields.py` | Output maps live in `contracts/asset_services.py` |
| `docs/AS_Field_Contract.md` | Read the contract module or live MCP schema |
| `scripts/generate_as_field_contract_doc.py` | No generated mapping document is required |
| `tests/test_as_field_contract_doc.py` | Contract and live-schema tests cover behavior |
| `tools/health_tools.py` and `models/health.py` | The independent `GET /ready` endpoint remains |

### 3.4 Current implementation tree

```text
main.py
octobot_mcp/
  server.py
  contracts/
    common.py
    asset_services.py
  tools/
    asset_services_tools.py
  runtime/
    service_tool_runtime.py
  services/
    provider_query_service.py
  config/
    service_schema_registry.py
    environment.py
    log_filters.py
  models/
    provider_query.py
  utils/
    request_context.py
    time_logger.py
tests/
  test_asset_services_contracts.py
  test_asset_services_tool_schema.py
  test_asset_services_tools.py
  test_tools.py
```

This is the current grouped layout. There is no separate `startup.py`,
`contract_validator.py`, Events tool module, Cash tool module, response
normalizer module, or error normalizer module. Those responsibilities are
composed in the current contract, tool, runtime, and provider service files.

## 4. Startup call path

Startup establishes the runtime before the first business request arrives.

### Step 1: process entry

File: `main.py`

The process loads deployment configuration and starts the application. This is
composition code, not business-field logic. A change to an Events output name
does not belong here.

### Step 2: server composition

File: `octobot_mcp/server.py`

The server connects:

- request/auth/tracing middleware;
- the `GET /ready` HTTP endpoint;
- the provider client and `ProviderQueryService`;
- the Asset Services tool registrar;
- the MCP transport endpoint.

The readiness endpoint is not an MCP tool and does not enter the agent tool
inventory.

### Step 3: typed environment settings

File: `octobot_mcp/config/environment.py`

The loader resolves environment-owned settings such as provider base URL,
authentication, certificates, HTTP timeouts, retry policy, and total AS tool
deadline. The tool deadline must come from the active environment configuration,
not from a hard-coded branch-specific value.

### Step 4: common contract type validation

File: `octobot_mcp/contracts/common.py`

`FieldContract` describes one business field, including:

- business key;
- internal provider column;
- value type;
- whether it is required;
- whether it is selectable;
- whether it is filterable;
- approved aliases.

`ServiceToolContract` groups those fields for one tool and adds its tool name,
domain, service portable ID, default outputs, and maximum agent limit.

`ServiceToolContract.__post_init__` performs fail-fast consistency checks. The
Asset Services module also runs its contract-level validation during import
(reported as `validate_asset_services_contracts()`). For example, default
output fields must exist and be selectable, mappings must be unambiguous, and
limits must be internally valid. An invalid contract prevents startup instead
of creating a partially functioning tool.

### Step 5: Asset Services contract loading

File: `octobot_mcp/contracts/asset_services.py`

This module constructs:

- `EVENTS_ENTITLEMENTS_CONTRACT`;
- `CASH_ENTITLEMENTS_CONTRACT`;
- `EVENTS_ENTITLEMENTS_OUTPUT_FIELDS`;
- `CASH_ENTITLEMENTS_OUTPUT_FIELDS`;
- output-field types used by the two tool schemas;
- `SAFE_ACCOUNT_ALIASES`;
- the agent and provider limit constants.

The mappings are checked-in code. There is no database call or runtime mapping
generation during startup.

### Step 6: tool registration

File: `octobot_mcp/tools/asset_services_tools.py`

`AssetServicesTools._register_tools` publishes exactly:

- `query_as_events_entitlements`;
- `query_as_cash_entitlements`.

Their explicit typed signatures become the MCP JSON schemas visible to the AS
Specialist. Internal contract details are captured by the wrappers but are not
tool arguments.

### Step 7: server ready

The MCP endpoint can now answer `list_tools` and tool calls. The external
readiness endpoint can report process readiness independently.

## 5. Agent stage: user to typed tool call

Use this example only to understand structure:

```text
Retrieve the event type and payment status for event 2026656277 and
Safe Account 0008001820000.
```

### Step 1: Executor invokes Root Orchestrator

File: `Octobot_Root_Orchestrator_System_Prompt.yaml`

The Root:

1. recognizes Asset Services event intent;
2. preserves `2026656277` exactly;
3. preserves `0008001820000` exactly;
4. removes any unsupported styling request from the business intent;
5. returns route `ASSET_SERVICES`;
6. does not choose a tool or provider field.

Conceptual handoff:

```json
{
  "intent": "Retrieve the requested event facts for the supplied event and Safe Account.",
  "route": "ASSET_SERVICES",
  "targetDomains": ["ASSET_SERVICES"],
  "specialistTask": "Retrieve event type and payment status for event 2026656277 and Safe Account 0008001820000.",
  "conversationContext": [],
  "directResponse": "",
  "clarificationQuestion": "",
  "presentationNoticeRequired": false
}
```

All values are JSON primitives. In particular, `route` is a string, not a
Python enum instance.

### Step 2: Executor invokes AS Specialist

File: `Octobot_Asset_Services_Specialist_System_Prompt.yaml`

The Specialist:

1. confirms the AS route;
2. chooses `query_as_events_entitlements` from the requested facts;
3. maps the approved phrase `Safe Account` to the tool parameter
   `safe_account`;
4. preserves the identifier as a digit string, including leading zeroes;
5. verifies all required parameters in the live tool schema;
6. selects only allowed requested fields for event type and payment status;
7. calls the typed MCP tool once.

The Specialist does not send:

- a service portable ID;
- a provider column name;
- a provider URL;
- an equality operator;
- a raw filter expression;
- credentials;
- a `request_id` or correlation ID.

## 6. Events tool: method-by-method path

### Step 1: MCP schema validation

Boundary: MCP framework/Pydantic-generated tool schema

Before wrapper execution, the transport validates that supplied arguments match
the registered function schema. Structurally invalid calls do not become
provider requests.

### Step 2: registered Events wrapper

File: `octobot_mcp/tools/asset_services_tools.py`

Method boundary: registered `query_as_events_entitlements` wrapper

The wrapper receives only business arguments. It gathers supplied filters and
requested fields, binds `EVENTS_ENTITLEMENTS_CONTRACT`, and delegates to the
shared runtime.

### Step 3: request correlation lookup

File: `octobot_mcp/utils/request_context.py`

Method: `RequestContext.correlation_id()`

The current correlation ID comes from middleware/request context. The agent
cannot choose it. It is used for internal tracing and safe MCP response
correlation, then excluded from the Specialist and final user response.

### Step 4: deadline lookup

File: `octobot_mcp/tools/asset_services_tools.py`

Method: `_deadline_seconds`

The wrapper resolves the configured total deadline for the call. This deadline
encloses validation, provider work, retries, retry delays, and normalization.

### Step 5: enter shared execution

File: `octobot_mcp/runtime/service_tool_runtime.py`

Method: `execute_service_tool`

Inputs conceptually include:

```text
contract          = EVENTS_ENTITLEMENTS_CONTRACT
values            = supplied business filters
requested_fields  = approved Events output selections
limit              = validated caller value or default
offset             = validated caller value or default
correlation_id     = request context
deadline           = configured total duration
provider_service   = shared ProviderQueryService
```

The runtime rejects invalid `limit` or `offset` values. It does not silently
clamp a request into a different request.

### Step 6: resolve selected outputs

File: `octobot_mcp/runtime/service_tool_runtime.py`

Method: `_resolve_select_columns`

This helper:

1. uses contract defaults when `requested_fields` is omitted;
2. verifies every requested business key exists;
3. verifies every requested key is selectable for Events;
4. returns safe `INVALID_OUTPUT_FIELDS` when validation fails;
5. maps accepted business keys to provider columns internally.

It cannot select `safe_account` for Events because that Events field is
filter-only. This is a contract difference, not a missing generic capability.

### Step 7: build filters

File: `octobot_mcp/runtime/service_tool_runtime.py`

Method: `_build_filter_expressions`

This helper:

1. checks all Events-required business filters;
2. ignores optional parameters that were not supplied;
3. validates value type and field constraints;
4. verifies each supplied field is filterable;
5. rejects unknown fields;
6. rejects comma-containing values until provider list/OR grammar is verified;
7. maps accepted business keys to provider columns;
8. creates structured equality-only `FilterExpression` objects.

Because the operator is constructed by code, a user string cannot replace `EQ`
or inject a second provider expression.

### Step 8: construct provider model

File: `octobot_mcp/models/provider_query.py`

Types: `FilterExpression`, `ProviderQueryRequest`

The runtime creates a structured request from validated data. The request model
keeps columns, expressions, limit, and offset as separate typed fields. It does
not concatenate user values into one executable filter string.

### Step 9: call shared provider service

File: `octobot_mcp/services/provider_query_service.py`

Class: `ProviderQueryService`

The provider service:

1. obtains the internal service configuration;
2. encodes each structured filter expression using provider grammar;
3. constructs the HTTP request;
4. attaches deployment-owned authorization and correlation headers;
5. applies network timeout and bounded retry rules;
6. never exceeds the one total tool deadline;
7. returns the provider response or raises/returns a typed provider failure.

The agent limit remains 100 even though the provider transport accepts a much
larger internal ceiling. The provider ceiling is not exposed as a tool choice.

### Step 10: normalize success

File: `octobot_mcp/runtime/service_tool_runtime.py`

Method: `_normalize_success`

This helper:

1. reads only expected provider rows;
2. maps provider columns back to approved business keys;
3. preserves identifier strings and returned values;
4. retains safe pagination data;
5. returns `NO_DATA` when no rows match;
6. returns the common success envelope otherwise.

Provider columns are gone before records leave the MCP runtime.

### Step 11: normalize provider failure

File: `octobot_mcp/runtime/service_tool_runtime.py`

Methods: `_normalize_provider_error` and `_error_result`

These helpers convert known provider failures into safe error codes, messages,
and retryability. Unexpected failures become `INTERNAL_TOOL_ERROR`. Deadline
expiry becomes `TOOL_TIMEOUT` with the fixed safe message.

They exclude raw response bodies, stack traces, URLs, credentials, internal
columns, filter expressions, and exception text from the agent-facing result.

## 7. Return path through the agents

### Step 1: Specialist reads the tool status

The AS Specialist reads `status` before `records`:

- `SUCCESS`: copy records and safe pagination;
- `NO_DATA`: preserve no-data and keep records empty;
- `NEEDS_CLARIFICATION`: ask for the safe missing business input;
- `ERROR`: copy only safe `code`, `message`, and `retryable` fields.

It then returns one `asset_services_result`. A single-service success contains
one `serviceResults` item. Two requested services remain two separate items.

### Step 2: Executor invokes Formatter

File: `Octobot_Final_Response_Formatter_System_Prompt.yaml`

The Formatter receives `root_handoff` and `asset_services_result`. It calls no
tools and does not repair missing business facts.

For a successful Events result it:

1. creates one table;
2. keeps the business columns in source order;
3. keeps records in source order;
4. creates one string cell per column;
5. uses `null` for a missing or null approved value;
6. adds exactly one `<<table_1>>` placeholder to `answer`;
7. copies the actual tool name into `toolsUsed`;
8. returns exactly one final `schema` JSON object.

### Step 3: HTML-safe presentation

The Formatter treats every incoming string as data. It does not execute or
reproduce embedded presentation instructions. It emits no HTML, XML, CSS,
JavaScript, style attribute, custom tag, or entity-encoded tag.

The only allowed angle-bracket syntax is a table placeholder such as
`<<table_1>>`. If the user asked for unsupported styling, the fixed
standard-format notice appears once before the business result.

### Step 4: Executor persistence and UI rendering

The final `schema` uses JSON-native values only. It is safe to persist to JSONB.
The UI replaces each table placeholder with the matching structured table. It
does not need to parse HTML from the agent.

## 8. Cash request differences

The Cash path uses the same shared files and methods, but starts with:

- registered wrapper `query_as_cash_entitlements`;
- `CASH_ENTITLEMENTS_CONTRACT`;
- `CASH_ENTITLEMENTS_OUTPUT_FIELDS`;
- the Cash output-field type or allowlist.

Important differences:

| Concern | Events | Cash |
|---|---|---|
| Business focus | Event terms, status, dates, options | Account-level amounts, tax, currency, and payment facts |
| Required filters | Tool schema requires the verified Events inputs | Current schema establishes no required business filter |
| `safe_account` output | Not selectable; filter-only provider field | Selectable when allowed by Cash schema |
| Output mapping size | 38 entries | 121 entries |

An unfiltered Cash call is valid only when the user explicitly requests broad
results and the live schema permits it. The Specialist must not manufacture a
filter simply because Events has required filters.

## 9. Two-tool request and partial success

For a request that genuinely needs Events and Cash:

```text
AS Specialist
  -> call Events tool
  -> call Cash tool
  -> keep the two results separate
```

The tools may be independent, but orchestration belongs to the Specialist, not
the shared MCP runtime.

| Events | Cash | Specialist status | Formatter behavior |
|---|---|---|---|
| Success | Success | `SUCCESS` | Render two separate tables |
| Success | Error | `PARTIAL_SUCCESS` | Keep Events table; add safe Cash failure attribute |
| Error | Success | `PARTIAL_SUCCESS` | Keep Cash table; add safe Events failure attribute |
| Error | Error | `FAILED` | No record table; show a safe failure |
| No data | No data | `NO_DATA` | Explain no matching records; no empty table |

No layer silently discards a successful sibling result.

## 10. Controlled failure paths

### Missing required business input

```text
Specialist reads live schema
  -> identifies missing business parameter
  -> does not call affected tool
  -> returns NEEDS_CLARIFICATION with one grounded question
  -> Formatter renders question and grounded choices, if any
```

### Invalid output field

```text
_resolve_select_columns
  -> requested key absent or not selectable
  -> INVALID_OUTPUT_FIELDS
  -> no provider call
  -> safe failure reaches Formatter
```

### Invalid filter value or attempted filter injection

```text
_build_filter_expressions
  -> type, pattern, comma, or filterability check fails
  -> INVALID_PARAMS
  -> no provider call
  -> no raw expression is exposed
```

### Timeout

```text
configured total deadline expires
  -> stop additional retries
  -> normalize to TOOL_TIMEOUT
  -> Specialist does not retry
  -> Formatter returns fixed safe timeout text
```

### Provider error

```text
ProviderQueryService receives HTTP/provider failure
  -> _normalize_provider_error
  -> safe code/message/retryable only
  -> raw provider details remain in redacted internal logs
```

### Unexpected runtime error

```text
unexpected exception
  -> _error_result
  -> INTERNAL_TOOL_ERROR
  -> no stack trace or exception text in agent output
```

### Malformed agent handoff

```text
Formatter detects missing or contradictory structured input
  -> final FAILED
  -> error = INVALID_FORMATTER_INPUT
  -> no attempt to reconstruct records
```

### Non-JSON executor state

```text
agent schema emits a Python enum or another runtime object
  -> JSONB serialization would fail
```

The current prompts prevent this by defining route and status fields as plain
strings and keeping every handoff value JSON-native.

## 11. Where to debug

| Symptom | First file/boundary to inspect | What to verify |
|---|---|---|
| Wrong domain route | Root prompt | Route definitions and preserved intent |
| AS tool not called | AS Specialist prompt and live tool schema | Route, required input, and allowlist |
| Wrong tool selected | AS Specialist prompt | Events versus Cash business scope |
| Tool missing from inventory | `tools/asset_services_tools.py`, server composition | `_register_tools` and imports |
| Extra legacy tool appears | Tool inventory test and server registration | Exactly two tools are registered |
| Required parameter mismatch | Registered wrapper and `contracts/asset_services.py` | Signature and contract agree |
| Wrong output field accepted | `_resolve_select_columns` and AS contract | Selectable flag and output allowlist |
| Wrong provider filter | `_build_filter_expressions` and AS contract | Business-to-provider mapping and equality operator |
| Filter injection concern | `FilterExpression` construction and provider encoder | No raw agent filter string reaches encoder |
| Leading zero lost | Tool schema, runtime validation, request model | Identifier remains a string end to end |
| `SN` appended | Root/AS prompt and filter builder | Identifier preservation rules |
| Too many records requested | AS contract and runtime pagination validation | `AGENT_MAX_RESULT_LIMIT = 100` |
| Tool hangs | Environment config, `_deadline_seconds`, provider retry path | One total deadline encloses retries |
| Unsafe provider error visible | Normalization helper and log redaction | Safe code/message only |
| Provider field appears in result | `_normalize_success` and output map | Reverse mapping to business key occurred |
| Events returns `safe_account` | Events output contract | Field must remain non-selectable |
| Cash cannot return `safe_account` | Cash output contract | Selectable mapping exists |
| Empty result shown as failure | Specialist and Formatter status mapping | `NO_DATA` maps to final success without a table |
| Successful sibling disappeared | Specialist partial-success construction | Preserve each successful service item |
| HTML or styling appears | Formatter prompt | Fixed presentation contract and escaping |
| Table row/column mismatch | Formatter prompt/output validator | One cell per column and one placeholder per table |
| JSONB serialization failure | Agent output schema and executor conversion | Only JSON-native primitives enter state |
| Readiness fails | `server.py` and `GET /ready` path | Do not inspect MCP tool inventory first |

## 12. Test map

The latest supplied test report identifies these useful verification areas:

| Test file or area | Expected guarantee |
|---|---|
| `tests/test_asset_services_contracts.py` | Required/selectable/filterable rules, mappings, aliases, defaults, and limits are valid |
| `tests/test_asset_services_tool_schema.py` | Agent-visible signatures expose only approved fields, descriptions, constraints, and limits |
| `tests/test_asset_services_tools.py` | Events and Cash wrappers delegate correctly and normalize outcomes |
| `tests/test_tools.py::test_exact_tool_inventory` | Only the two current AS tools are registered |
| Provider query service tests | Structured filters, transport, retries, and error behavior |
| Service schema registry tests | Internal provider schema configuration remains valid |
| Readiness endpoint test | `GET /ready` remains available independently |
| Auth/middleware tests | Request security and context behavior remain intact |
| Formatter end-to-end QA cases | HTML safety, table fidelity, no-data, nulls, errors, and partial success |

Latest reported local result: 84 tests passed, the literal CI entry point exited
0 with coverage output, and repository lint passed. The external three-agent
end-to-end result must be recorded separately when it completes.

## 13. Change ownership guide

Use this rule when modifying the system:

| Change | Correct owner |
|---|---|
| Add or rename an agent route | Root prompt and executor route wiring |
| Add an AS business input | AS contract, typed wrapper, tests, and prompt only if terminology changes |
| Add an AS output field | `contracts/asset_services.py`, output schema/type, normalization tests |
| Change a provider column | AS contract only; do not expose it to prompts |
| Change filter grammar | Runtime/provider-query layer plus security tests |
| Change result cap | AS contract, typed schema constraints, runtime validation, docs |
| Change total deadline | Typed environment config and deadline tests |
| Change provider retry behavior | `ProviderQueryService` and deadline tests |
| Change final table contract | Formatter prompt, executor/UI contract, end-to-end QA tests |
| Add Transaction Management | New explicit TM contracts/tools/specialist plus Root route activation |

Do not create a second output mapping module or generated mapping document. A
new domain may reuse common contract/runtime types, but each business service
must still expose an explicit typed tool and own a reviewed code-defined
contract.
