# Refactor Asset Services MCP Into a Clean Shared AS/TM Foundation

Work directly in the current repository. First inspect the existing implementation, tests, schema registry, deployment configuration, and attached architecture documents. Do not invent service columns, identifiers, validation rules, limits, error formats, retry behavior, or business requirements.

## Objective

Refactor the implementation into a clean, fresh foundation shared by:

- Asset Services now.
- Transaction Management later.
- One common provider-query service and execution runtime.
- Explicit, typed MCP tools.
- Code-defined tool contracts.
- No PostgreSQL or runtime metadata database.

Implement only the two Asset Services tools in this change:

- `query_as_events_entitlements`
- `query_as_cash_entitlements`

Do not implement placeholder TM tools or fabricate TM schemas.

## Required Architecture

Use these names unless existing repository conventions require an equivalent:

- `config/service_schema_registry.py`
- `contracts/common.py`
- `contracts/asset_services.py`
- `models/provider_query.py`
- `services/provider_query_service.py`
- `runtime/service_tool_runtime.py`
- `tools/asset_services_tools.py`

The common modules must not contain Asset Services-specific logic. TM must later be able to add contracts and wrappers while reusing the same provider service and runtime.

The tool wrappers must remain thin:

1. Declare typed, agent-visible parameters.
2. Pass values and a code-defined contract to `execute_service_tool()`.
3. Return its structured result unchanged.

## Remove Superseded Code

Move required behavior before deleting the old implementation. Remove:

- `ApigeeService`, `ApigeeTools`, and their exports.
- `apigee_service.py`
- `apigee_tools.py`
- `models/apigee.py`
- `apigee_schema_registry.py`
- Generic agent-visible dictionary, filter-value, and `apply_filters` tools.
- The AS-specific runtime after its reusable logic is moved to `service_tool_runtime.py`.
- Obsolete tests, imports, comments, compatibility aliases, and dead configuration.

Rename internal concepts consistently:

- `ApigeeService` to `ProviderQueryService`.
- `ApigeeEnvironment` to `ProviderApiEnvironment`.
- `ApplyFiltersRequest` to `ProviderQueryRequest`.
- `apigee_schema_registry` to `service_schema_registry`.

Update server registration, package exports, tests, Helm templates, environment settings, and documentation atomically. Do not rename externally managed URLs, secret paths, or infrastructure values unless every deployment reference can safely be migrated. Report any external name that must remain.

Do not delete unrelated authentication middleware, request context, health endpoints, logging, or shared utilities that remain necessary.

## Source-of-Truth Audit

Before editing, create an evidence table containing:

- Tool.
- Business parameter.
- Required or optional.
- Verified type and validation.
- Canonical provider column.
- Source file and line.
- Selectable/filterable status.
- Approved aliases.

Use the existing Asset Services implementation and service dictionary as factual sources. Merely finding a provider column in the registry does not prove it is an approved agent-visible parameter.

If a fact cannot be verified, do not guess. List it in the completion report.

## Tool Contracts

Required provider filters must be required Python parameters. Expose every business-approved optional filter as an explicit named parameter.

For every parameter, use `Annotated` and `Field` so the generated MCP JSON schema includes:

- Description.
- Required/optional status.
- Type.
- Verified format, pattern, enum, and length constraints.
- Examples only when existing code supplies verified examples.

Do not rely only on function docstrings for parameter descriptions.

Remove the numeric restriction from `event_id` unless the existing source proves it. Do not retain invented maximum lengths.

For Safe Account:

- Expose one canonical MCP parameter named `safe_account`.
- Document `Safe Account`, `Safe Account Number`, `Security Account`, and `Security Account ID` as synonyms.
- Resolve it to the verified canonical column through the service dictionary.
- Require digits only.
- Preserve the supplied string exactly, including leading zeroes.
- Reject suffixes such as `8001820000 SN` before any provider call.
- Never append, remove, translate, or infer characters.

Do not duplicate alias lists independently across the registry, contract, prompt, and tool. Define them once and reuse them.

## Safe Query Construction

Do not construct filters using unchecked string interpolation such as:

```python
f"{provider_column}={value}"
```

Use a structured filter representation and the existing verified provider grammar. Validate or safely encode values so delimiters, operators, quotes, spaces, and URL characters cannot alter query semantics.

Column names must only come from the code-defined allowlist. Values must remain values and must never become filter syntax.

Unknown fields must return `INVALID_PARAMS`; they must not be silently ignored.

## Pagination And Output

Define schema and runtime validation for:

- `limit > 0`
- `offset >= 0`
- A verified upper limit only if an actual maximum is established by current source.

Do not treat a request model’s default `take` value as a maximum. Do not silently clamp invalid values.

Resolve `requested_fields` through an allowlist. Normalize provider rows to documented business-facing field names unless the existing Formatter contract explicitly requires canonical provider names. Preserve the current final production JSON contract.

## Error Handling

Every expected failure must return the existing structured tool result, including:

- `status`
- `toolName`
- `domain`
- `correlationId`
- `records`
- `error.code`
- `error.message`
- `error.retryable`
- `error.details`

Build provider error responses from an explicit allowlist. Never copy an entire provider payload into the tool response.

Handle:

- Invalid parameters.
- Unknown filters or output fields.
- Authentication failures.
- Provider 4xx and 5xx responses.
- Network failures.
- Malformed provider responses.
- Timeouts.
- Unexpected internal failures.

Return a sanitized `INTERNAL_TOOL_ERROR` for unexpected failures and log technical details only server-side. Never expose credentials, raw provider bodies, stack traces, internal URLs, or raw filter expressions.

Always re-raise `asyncio.CancelledError`.

## Deadline

Keep one required, positive, per-environment tool deadline in YAML and environment settings. Do not add an invented Python default.

The same deadline must cover:

- Local validation.
- Request construction.
- Authentication and any existing approved retry.
- Provider round trip.
- Response normalization.

When exceeded:

- Cancel in-flight work.
- Do not start another retry.
- Return `TOOL_TIMEOUT`.
- Set `retryable=true`.
- Return: `The request took longer than the configured time limit. Please try again.`

Remove `cash_entitlements_require_filter` and its YAML setting unless an approved requirement predating this branch proves the gate is required. The verified Cash contract currently has zero required filters, so do not invent one.

## Tool Exposure

The Asset Services Agent must receive only:

- `query_as_events_entitlements`
- `query_as_cash_entitlements`

Remove or prevent access to generic provider tools that bypass typed contracts. Preserve health tooling only where operationally required.

## Tests

Add focused tests proving:

- Generated MCP schemas contain correct required fields, descriptions, types, aliases, enums, and pagination constraints.
- Contract columns match the registry at startup.
- Required fields are rejected before HTTP.
- Safe Account preserves `8001820000` and `000123`.
- `8001820000 SN` is rejected with zero HTTP calls.
- Reserved filter characters cannot change query semantics.
- Unknown inputs are rejected rather than ignored.
- Invalid limits and offsets are rejected rather than clamped.
- Success and no-data normalization.
- Business/output-field mapping.
- Safe provider 4xx, 5xx, authentication, network, malformed-response, and internal errors.
- Deadline cancellation, one total budget, no post-timeout retry, and the exact timeout message.
- Only the two AS query tools are available to the AS Agent.
- No database call occurs during startup or requests.

Run the repository’s actual CI test entry point, complete test suite, linter, and formatter.

## Documentation

Update `Octobot_MCP_API_Function_Flow.md`, README, and architecture documentation to show:

`AS Agent -> typed AS tool -> common service-tool runtime -> provider query service -> provider API`

Also show TM as a future consumer of the common runtime, without adding TM implementation.

Remove PostgreSQL and old Apigee implementation references from the application flow.

## Completion Report

Return:

1. Files added, renamed, changed, and deleted.
2. Old-to-new naming map.
3. Evidence table for every AS parameter and constraint.
4. Generated JSON schema for both MCP tools.
5. Redacted success, validation-error, provider-error, and timeout traces.
6. Exact test, coverage, lint, and formatting results.
7. Search results proving no references remain to `ApigeeService`, `ApigeeTools`, `apigee_service`, `apigee_tools`, or `models.apigee`.
8. Confirmation that the AS Agent is restricted to the two AS tools.
9. Every unresolved business fact or external dependency.

Do not claim Agent-to-Formatter-to-UI end-to-end verification unless those components were actually executed. Stop and report conflicts instead of resolving them through assumptions.