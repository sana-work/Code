# GitHub Copilot Implementation Brief: Asset Services MCP Tools

Date: 2026-09-06

Status: implementation prompt for GitHub Copilot coding agent

## 1. How to use this file

Give this entire file to GitHub Copilot in the repository that contains the
existing Octobot MCP code. Also attach or place these architecture references
in the repository:

- `Updated_Proposed_Octobot.png`
- `Octobot_MCP_API_Function_Flow.md`

Copilot must inspect the repository before changing code. The examples in this
document describe structure and behavior; they are not permission to invent
provider details.

---

## 2. Prompt for GitHub Copilot

You are implementing the first phase of the revised Octobot architecture.
Build and verify only the two Asset Services MCP tools and the small set of
common functions they require. Do not implement Transaction Management tools
in this phase.

Work directly in the existing Octobot MCP repository. There is already working
Asset Services code using the generic tools `get_filter_values`,
`get_service_dictionary`, and `apply_filters`. Previous fixes were made to
service resolution, column validation, provider error handling, retries, and
log redaction. Reuse that current implementation and preserve those fixes.

Do not replace working authentication, HTTP transport, request-context,
correlation-ID, timeout, exception, or logging infrastructure unless a focused
change is required for the two new tools.

Read these architecture files before implementation:

1. `Updated_Proposed_Octobot.png`
2. `Octobot_MCP_API_Function_Flow.md`

The target architecture has no PostgreSQL metadata integration. Tool
definitions, required fields, optional fields, provider mappings, service
portable IDs, aliases, defaults, and validation rules live in Python code and
are released with the MCP server.

### Primary objective

Add these service-specific MCP tools:

```text
query_as_events_entitlements
query_as_cash_entitlements
```

Each tool must expose its own verified required and optional business fields as
typed MCP function parameters. The generated MCP JSON Schema must therefore
tell the Asset Services Agent:

- which tool to select;
- which input values are required;
- which filters are optional;
- each parameter's business meaning and accepted terminology;
- each parameter's type and constraints;
- which output fields can be requested.

The agent must not send service names, portable IDs, provider columns, provider
URLs, raw provider filter expressions, or infrastructure context such as a
correlation ID. Obtain request and correlation identifiers from the existing
request-context/middleware mechanism unless the current verified MCP contract
already requires an explicit caller-supplied value.

### Definition of done

This phase is complete only when both new Asset Services tools:

1. are registered and visible through MCP tool discovery;
2. expose accurate typed parameter schemas derived from current repository
   facts;
3. call the existing provider successfully through shared code;
4. return normalized structured results;
5. preserve the existing authentication, timeout, retry, safe-error, logging,
   and correlation-ID behavior;
6. enforce a total tool-execution deadline loaded from the active
   environment's YAML configuration;
7. return every expected failure as an agent-visible, safe structured result,
   including an actionable timeout message that reaches the user;
8. pass unit, schema, service, and nonproduction end-to-end tests;
9. can be used by the current Asset Services Agent without calling the old
   discovery/dictionary workflow;
10. do not change the Formatter Agent or final production JSON/UI contract.

Do not stop after planning. Implement, test, run the server locally where the
repository supports it, and provide the completion report in Section 15.

---

## 3. Source-of-truth and non-invention rules

Use this precedence order whenever sources differ:

1. Current repository implementation and tests that are demonstrably used by
   the working Asset Services path.
2. Current service dictionaries, constants, or schemas already checked into
   the repository.
3. Current nonproduction runtime evidence and existing integration tests.
4. `Octobot_MCP_API_Function_Flow.md` for the target architecture.
5. Existing agent prompts for business routing and expected behavior.
6. Screenshots or historical documents only as diagnostic evidence.

Never invent or guess:

- a service portable ID;
- a provider column name or casing;
- whether a field is selectable or filter-only;
- whether a filter is required;
- an alias;
- a provider enum/code such as `MAND`, `VOLU`, or another abbreviation;
- a date format;
- an operator;
- default output fields;
- maximum provider pagination;
- provider response keys.

If a required fact cannot be proven from the current repository or an approved
provider contract, do not guess. Record it under `Unresolved contract facts` in
the completion report and stop only the affected tool. Continue implementing
and testing common code and any tool whose contract is fully verified.

Do not use the UUIDs, field names, or example values in screenshots as
authoritative configuration. Confirm every such value in the current code.

---

## 4. Mandatory repository inspection before edits

Locate symbols rather than relying on historical line numbers. At minimum,
inspect:

```text
octobot_mcp/models/apigee.py
octobot_mcp/services/apigee_service.py
octobot_mcp/tools/apigee_tools.py
octobot_mcp/config/apigee_schema_registry.py
or the actual registry file containing ServiceSchema and get_service_schema
octobot_mcp/utils/exceptions.py
octobot_mcp/utils/auth.py
octobot_mcp/utils/request_context.py
octobot_mcp/logconfig.yaml
octobot_mcp/config/log_filters.py, if present
octobot_mcp/server.py
octobot_mcp/main.py
all environment YAML files and the code that loads them
all existing tests related to Apigee and Asset Services
```

Find and understand these current symbols or their actual equivalents:

```text
GetFilterValuesRequest
ApplyFiltersRequest
ApigeeService
ApigeeTools
get_filter_values
get_service_dictionary
apply_filters
_authorized_get
_validate_request_schema
_build_filter_query
get_service_schema
supports_service_schema
ColumnSchema
ServiceSchema
CitiMCPToolError
InvalidParamsError
ServiceUnavailableError
```

Before editing, produce a short implementation inventory containing:

- the actual authoritative schema-registry filename;
- the two verified Asset Services service names;
- all aliases already accepted for each service;
- the exact portable ID source for each service;
- required filter fields for each service;
- optional filterable fields for each service;
- selectable output fields for each service;
- default output fields for each service;
- provider data types and accepted operators;
- current provider endpoint and method construction;
- current success response shape;
- current structured error shape;
- current retry and timeout behavior;
- current per-environment YAML hierarchy and configuration loader;
- current HTTP timeout and total tool-execution timeout, if different;
- where request and correlation identifiers originate and how tools access
  them without adding agent-visible parameters;
- current tests covering these facts.

Do not make code changes until this inventory is complete.

---

## 5. Current behavior that must be preserved

The current repository may use these canonical/alias names for Asset Services:

```text
view_events_entitlements
view_api_octobot_events_entitlements
view_cash_entitlements
view_api_octobot_cash_entitlements
```

Treat this list as a search aid only. Confirm the current canonical names,
aliases, and service-portable-ID pairs from the repository. Do not assign an
alias to a service merely because its name is similar.

Preserve all completed fixes found in the branch, including where present:

- canonical service-name normalization;
- validation that service name and portable ID belong to the same service;
- filtering discovery to services with supported local schemas;
- separation of selectable columns from filter-only columns;
- required-filter validation;
- typed filter-value validation;
- rejection of invalid account values before provider invocation;
- safe HTTP parameter encoding;
- structured provider errors;
- retry classification by status and transport failure;
- honoring `Retry-After` for `429`;
- bounded retries for retryable gateway/transport failures;
- no automatic retry of invalid requests or deterministic provider rejection;
- preservation of correlation IDs;
- redaction of credentials, URLs, account values, and sensitive query data;
- suppression of unsafe `httpx`/`httpcore` request logging;
- no exception chaining that exposes complete provider URLs.

The known malformed account pattern must remain impossible:

```text
sfacntnm=<digits> SN
```

Never silently strip `SN`. Validate the value according to the verified field
contract and reject invalid input locally without calling the provider.

---

## 6. Scope and non-goals

### In scope

- two new Asset Services MCP tools;
- code-defined contracts for those two tools;
- explicit typed tool parameters;
- small shared request-validation and provider-request-building functions;
- normalized common tool results;
- one total Asset Services tool deadline configurable through every supported
  environment YAML file;
- registration of the two tools;
- tests and documentation;
- minimal Asset Services Agent toolset configuration needed for end-to-end
  testing, if that configuration is in this repository.

### Out of scope

- Transaction Management tools;
- PostgreSQL or another metadata database;
- workbook loading at startup;
- dynamic metadata refresh;
- a generic framework for arbitrary future domains;
- rewriting the entire MCP server;
- replacing working authentication or HTTP infrastructure;
- changing the Formatter Agent;
- changing the final production JSON schema or UI rendering contract;
- removing the current generic tools before the new path is accepted;
- unrelated refactoring.

Prefer a few clear dataclasses/Pydantic models and functions over a large
abstraction hierarchy.

---

## 7. Target implementation shape

Follow existing repository conventions. The names below are recommendations,
not a requirement to reorganize working code unnecessarily.

```text
octobot_mcp/
  contracts/
    asset_services.py
    tool_result.py                 # reuse existing result model if present
  tools/
    asset_services_tools.py        # or extend current ApigeeTools cleanly
  services/
    asset_services_service.py      # optional thin layer
    apigee_service.py              # reuse existing provider execution
  tests/
    test_asset_services_tool_schema.py
    test_asset_services_tools.py
    test_asset_services_contracts.py
    test_asset_services_e2e.py
```

Do not create duplicate HTTP clients, authentication helpers, error models, or
request-context implementations.

### Keep the common implementation small

The shared code for this phase should need only these responsibilities:

```text
validate required and optional values
validate requested output fields
map business parameters to provider columns
build the provider request safely
call the existing authorized provider client
normalize records and errors
```

Avoid a repository class, plugin system, dependency-injection framework,
generic rule language, runtime schema compiler, or metadata cache.

---

## 8. Code-defined Asset Services contracts

Create one immutable contract for each Asset Services tool. Reuse the existing
schema dataclasses if they already express the required behavior cleanly.
Otherwise introduce only the minimum types needed, for example:

```python
@dataclass(frozen=True)
class FieldContract:
    parameter_name: str
    business_name: str
    provider_column: str
    data_type: str
    required: bool
    filterable: bool
    selectable: bool
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetServiceContract:
    tool_name: str
    service_name: str
    service_portable_id: str
    fields: Mapping[str, FieldContract]
    default_output_fields: tuple[str, ...]
    maximum_limit: int
```

Populate these contracts only from verified current code. Keep mappings
immutable after import.

At module import or server startup, validate:

- unique tool names;
- unique canonical business parameter names;
- unique normalized aliases within each service;
- nonblank service name and portable ID;
- every required parameter has a field contract;
- every default output is selectable;
- every requested-field enum member is selectable;
- every provider column is known to the current service schema;
- the function signature and contract keys agree.

Fail startup on an invalid code contract.

---

## 9. Agent-visible tool signatures

Define normal Python MCP functions, following the pattern shown in the supplied
CitiConnect example. Use typed parameters and detailed docstrings so MCP
generates useful JSON Schema for the agent.

### Required-parameter rule

Every filter the provider contract requires must be a required function
parameter with no default. Do not hide required inputs inside `filters`,
`entities`, `query`, `kwargs`, or a free-form dictionary.

### Optional-parameter rule

Every approved optional filter should be a named optional parameter. Do not
expose provider fields that are not filterable.

### Output-field rule

Expose requested output fields through a per-tool allowlist, enum, or
`Literal`. Do not accept arbitrary provider column strings. When omitted, use
the verified current default output columns.

### Representative structure

Do not copy the parameters below until they are verified against current code.
They demonstrate the intended function shape:

```python
@mcp_server.tool(tags={"AssetServices"})
async def query_as_events_entitlements(
    event_id: Annotated[str, Field(description="Required Event ID")],
    safe_account: Annotated[
        str,
        Field(
            pattern=r"^[0-9]+$",
            description=(
                "Required Safe Account. Security Account and Security Account "
                "ID are accepted business terms for the same identifier."
            ),
        ),
    ],
    requested_fields: list[EventsOutputField] | None = None,
    limit: int = 100,
    offset: int = 0,
    # Add verified optional filter parameters explicitly.
) -> ToolResult:
    ...
```

```python
@mcp_server.tool(tags={"AssetServices"})
async def query_as_cash_entitlements(
    # Add every verified required filter as a required parameter.
    requested_fields: list[CashOutputField] | None = None,
    limit: int = 100,
    offset: int = 0,
    # Add verified optional filter parameters explicitly.
) -> ToolResult:
    ...
```

For each real parameter, the docstring and schema description must state:

- business label;
- whether it is required;
- accepted business synonyms where approved;
- expected format;
- a synthetic example if useful;
- whether the value is a lookup criterion or output selector.

Do not include real account or event values in docstrings or tests.

Request IDs, correlation IDs, authentication values, and similar operational
metadata are not business query parameters. Read them through the repository's
existing request-context or middleware helper inside the wrapper/runtime. Do
not add them to either MCP input schema unless inspection proves that the
current public tool contract intentionally requires the caller to provide
them.

---

## 10. Tool execution flow

Each wrapper should remain short:

```python
# Obtain request_id from the existing request-context helper before this call.
return await asset_services_runtime.execute(
    contract=EVENTS_ENTITLEMENTS_CONTRACT,
    request_id=request_id,
    values={
        "event_id": event_id,
        "safe_account": safe_account,
        # Explicit optional parameters.
    },
    requested_fields=requested_fields,
    limit=limit,
    offset=offset,
)
```

The shared executor must:

1. validate the supplied business values against the selected code contract;
2. reject missing or invalid values before any provider call;
3. preserve string identifiers and leading zeroes;
4. validate output fields against the service-specific allowlist;
5. map business parameter names to exact provider columns;
6. use verified default outputs when no output list is provided;
7. build the request with structured HTTP parameters or the repository's safe
   current provider request builder;
8. call the existing `_authorized_get` or verified equivalent;
9. normalize provider records back to business field names;
10. convert expected failures into the current structured error contract.

Do not manually concatenate unvalidated user input into a URL.

### Configurable total tool deadline

The maximum duration of one MCP tool invocation must be configurable in the
active environment's YAML configuration. First reuse an existing equivalent
setting and configuration loader. If no total tool deadline exists, add one
clearly named Asset Services setting following the repository's current YAML
hierarchy, and add it to every supported environment file. Report the exact
key and value for each environment; do not create a second configuration
system or hard-code the production value in Python.

The configured value must:

- use one documented unit, preferably seconds if that matches current code;
- be parsed into a typed configuration object;
- be positive and within a reasonable repository-approved bound;
- fail startup with a clear configuration error when missing or invalid,
  unless the repository's existing configuration policy defines a safe
  default;
- apply to the complete tool invocation, including validation, provider calls,
  retry waits, retries, and response normalization;
- act as an overall deadline, so each retry cannot restart the full timer;
- cancel in-flight provider work when exceeded and prevent further retries.

Keep the lower-level HTTP connect/read timeout if the repository already has
one. The overall tool deadline and HTTP timeout have different purposes and
must not accidentally multiply the maximum user wait time.

### Agent-visible error propagation

No expected tool failure may exist only in logs or escape as an unhandled
exception. Normalize validation failures, provider rejections, exhausted rate
limits, transport failures, and deadline expiry into the existing common
`ToolResult` error shape. The result delivered over MCP must contain enough
safe information for the Asset Services Agent to explain the failure:

```text
status
stable error code
safe user-facing message
retryable true/false
tool name
correlation ID
```

Reuse the current field names and status vocabulary. Do not change the common
tool or final UI schema merely to match the labels above. Do not include stack
traces, credentials, provider response bodies, complete URLs, raw filters, or
unmasked identifiers.

For the overall deadline, use a stable internal error code such as the
repository's existing timeout code. If none exists, use `TOOL_TIMEOUT`. Its
agent-visible message must clearly state:

```text
The request took longer than the configured time limit. Please try again.
```

Mark this error retryable. Include the correlation ID through the existing
safe field so support can trace the request. Log the technical exception and
configured deadline internally with the same correlation ID, after applying
the current redaction rules.

For other failures, provide a similarly safe and actionable message based on
the normalized category. In particular:

- invalid input: identify the invalid or missing business field and do not
  advise retrying unchanged input;
- exhausted `429` retries: say that the service is temporarily limited and
  advise trying again later;
- provider or network unavailability: say that the service is temporarily
  unavailable and advise trying again;
- unexpected internal failure: provide a generic failure message and the
  correlation ID, without exposing implementation details.

Use the MCP library's current supported result mechanism so the agent actually
receives the error. Preserve structured content and provide a safe text content
fallback if required by the currently deployed MCP client. Verify this with an
MCP client test; do not assume that logging or raising an exception is visible
to the agent.

The Asset Services Agent must treat an error result as the outcome of that tool
call for the current turn. It must not invent records, claim success, or hide
the message. The Formatter Agent must map the error into the existing final
JSON fields and user-visible answer, with no data table for a failed call. The
timeout answer shown to the user must include the try-again guidance above.
This propagation must not change the existing production JSON/UI structure.

---

## 11. Safe Account terminology

Where the verified Asset Services contract uses this identifier, the
agent-visible parameter must be named consistently, preferably `safe_account`.
Its description must explain that these are approved equivalent user terms:

```text
Safe Account
Safe Account Number
Security Account
Security Account ID
```

The provider mapping remains internal. Confirm the exact provider column from
current code before configuring it.

Rules:

- retain the value as a string;
- preserve every digit, including leading zeroes;
- accept digits only when the current provider contract confirms a numeric
  identifier;
- reject suffixes, prefixes, embedded labels, or malformed values locally;
- do not silently repair malformed values;
- do not log the unmasked identifier;
- all approved user terms must result in the same tool parameter and provider
  condition.

---

## 12. Migration and compatibility

Keep `get_filter_values`, `get_service_dictionary`, and `apply_filters`
available during this phase unless the repository owner explicitly authorizes
their removal.

The new Asset Services Agent configuration should receive only:

```text
query_as_events_entitlements
query_as_cash_entitlements
```

Do not give the new Asset Services Agent the generic discovery/dictionary/filter
tools. This creates a clean end-to-end comparison while retaining rollback.

The old and new tool paths must share provider transport and error behavior.
Do not maintain two different authentication or HTTP implementations.

---

## 13. Testing requirements

### Tool-schema tests

For both tools, inspect the generated MCP JSON Schema and assert:

- the tool is registered under the exact target name;
- every verified required input appears in `required`;
- optional filters appear as named properties but not in `required`;
- descriptions contain approved business language;
- types, patterns, enums, limits, and defaults are correct;
- output fields are allowlisted;
- service names, portable IDs, and provider columns are not agent inputs.
- infrastructure context such as request/correlation IDs is absent unless the
  existing verified public tool contract requires it.

### Unit tests

Cover:

- missing required input;
- invalid identifier format;
- preservation of leading zeroes;
- approved Safe/Security Account terminology;
- invalid requested output field;
- default output selection;
- business-to-provider field mapping;
- filter-only fields never appearing in `$select`;
- selectable fields being accepted;
- pagination boundaries;
- provider not called after local validation failure;
- response mapping from provider names to business names;
- no-data response;
- structured provider errors.

### Existing defect regression tests

Retain or add tests proving:

- service aliases resolve to the correct canonical service;
- name and portable ID cannot come from different services;
- an account value with ` SN` is rejected before HTTP execution;
- provider `429` is classified as retryable and respects `Retry-After`;
- invalid request statuses are not retried;
- `502`, `503`, `504`, and timeouts use bounded retries;
- provider `500` is not retried by default unless the current approved policy
  explicitly says otherwise;
- the active environment YAML value controls the overall tool deadline;
- two environment configurations with different deadline values produce the
  corresponding runtime deadlines;
- an invalid or missing deadline fails according to the existing configuration
  policy;
- a deterministic slow provider crosses the deadline, cancels outstanding
  work, performs no later retry, and returns the normalized timeout result;
- retry attempts and `Retry-After` waits share one overall deadline rather than
  resetting it;
- the MCP client receives the safe structured error and any required text
  fallback;
- sensitive values and complete URLs are absent from logs and errors.

### End-to-end tests

Run the server using the repository's documented local method. Verify:

1. MCP tool listing contains both new Asset Services tools.
2. Tool schemas show the correct required and optional parameters.
3. An Events Entitlements request reaches the verified current provider service.
4. A Cash Entitlements request reaches the verified current provider service.
5. Safe Account and Security Account wording leads to the same parameter.
6. Successful results use normalized business field names.
7. No-data and provider errors use the structured result contract.
8. A forced deadline expiry reaches the Asset Services Agent with the stable
   timeout code, `retryable=true`, correlation ID, and try-again message.
9. The Formatter maps that timeout to the existing failed-response JSON and
   the UI displays the safe message without a table.
10. The current Asset Services Agent can complete both workflows.
11. Formatter output continues to satisfy the existing production JSON schema.

Use environment-supplied nonproduction test values such as
`AS_TEST_EVENT_ID` and `AS_TEST_SAFE_ACCOUNT`. Do not commit real identifiers.

---

## 14. Implementation sequence

Use this order to keep the change reviewable:

1. Inventory the current Asset Services contracts and existing fixes.
2. Add failing tests for the two generated MCP tool schemas.
3. Add minimal immutable code contracts for the two services.
4. Add startup contract validation.
5. Add or adapt the shared value validator and provider request builder.
6. Wire the typed per-environment total tool deadline through the existing
   configuration loader.
7. Add shared deadline enforcement and agent-visible error normalization.
8. Implement `query_as_events_entitlements` as a thin wrapper.
9. Run its unit and mocked service tests.
10. Implement `query_as_cash_entitlements` using the same shared functions.
11. Run its unit and mocked service tests.
12. Register both tools and inspect the generated MCP schemas.
13. Run the complete existing test suite.
14. Run nonproduction provider smoke tests.
15. Run the current Asset Services Agent end to end with only the two new tools.
16. Force a timeout and verify the message through the Formatter and UI schema.
17. Verify formatter/final JSON compatibility.
18. Update README tool inventory and produce the completion report.

Keep functions focused and plainly named. Split a function when it performs
multiple independent responsibilities, but do not introduce abstractions that
are unused by the two Asset Services tools.

---

## 15. Required completion report

When implementation is finished, return the following report. Include enough
detail that another reviewer can verify the flow without guessing. Redact
credentials, tokens, provider URLs, portable IDs if organizational policy
requires it, and all real account/event values.

### A. Repository and revision

```text
Repository:
Branch:
Base commit:
Final commit:
Python version:
MCP/FastMCP version:
```

### B. Files changed

Provide `git diff --stat` and a one-sentence purpose for every changed or added
file.

### C. Verified current Asset Services contracts

Provide one table per tool:

| Business parameter | Required | Python type | Accepted aliases | Internal provider column | Filterable | Selectable | Source file/line proving it |
| --- | --- | --- | --- | --- | --- | --- | --- |

Also provide:

```text
Canonical service name:
Accepted service aliases:
Portable ID source location:
Default output fields:
Maximum limit:
Provider endpoint construction location:
Request/correlation ID source:
```

Do not omit the source file and line evidence.

### D. Registered MCP schemas

Include the complete generated input JSON Schema for:

```text
query_as_events_entitlements
query_as_cash_entitlements
```

### E. Execution flow

List the exact functions called for one successful request:

```text
MCP wrapper
  -> contract/value validation
  -> provider request construction
  -> authorized HTTP call
  -> provider response normalization
  -> ToolResult
```

Include file paths and symbol names.

### F. Provider request evidence

For one redacted successful request per tool, provide:

- business-level tool input;
- resolved internal field names;
- redacted provider parameters;
- HTTP status;
- correlation ID;
- normalized tool status;
- normalized output field names.

Do not include tokens, complete URLs, or unmasked account/event identifiers.

### G. Error behavior

Show one example each for:

- local validation error where the provider was not called;
- no-data result;
- provider rejection;
- retryable `429` or mocked equivalent;
- timeout or mocked equivalent.

For the timeout example, also provide:

```text
Configuration file and exact YAML key:
Configured deadline and unit:
Measured tool duration:
Number of provider attempts:
Whether in-flight work was cancelled:
Agent-visible ToolResult:
Formatter output using the existing final schema:
Exact safe message displayed to the user:
Correlation ID present and secrets absent:
```

Show the configured key/value for every supported environment and prove that
the active environment selects the intended value.

### H. Tests

Provide the exact commands and complete summaries:

```text
Focused Asset Services tests:
Full repository tests:
Lint/format/type checks:
Nonproduction smoke tests:
```

List skipped, failed, or unavailable checks explicitly.

### I. Agent end-to-end verification

Provide redacted evidence for:

1. Events Entitlements request.
2. Cash Entitlements request.
3. Safe Account wording.
4. Security Account wording.
5. Missing required input clarification.
6. Unsupported field rejection.
7. Formatter/final JSON validation.
8. Forced timeout propagated from tool to agent to formatter to UI response.
9. Non-timeout provider failure propagated without leaking provider details.

### J. Compatibility and rollback

State:

- whether the old generic tools remain registered;
- how the new Asset Services Agent receives only the two target tools;
- whether the final UI JSON contract changed; expected answer is no;
- the rollback method;
- any feature flag used.

### K. Unresolved contract facts

List every detail that could not be proven from current code. Write `None` only
when all service fields, mappings, required rules, defaults, and provider values
were verified.

### L. Final diff

Attach or paste:

```text
git status --short
git diff --check
git diff <base-commit>...HEAD
```

If the complete diff is too large, provide the commit hash plus focused diffs
for contracts, tool wrappers, shared execution, registration, and tests.

---

## 16. Review checklist for Copilot

Before reporting completion, confirm every item:

```text
[ ] Only Asset Services target tools were implemented.
[ ] No PostgreSQL or metadata-loader code was introduced.
[ ] Current provider facts were reused and cited by source file/line.
[ ] No portable ID, column, alias, enum, or required filter was invented.
[ ] Required filters are required MCP function parameters.
[ ] Optional filters are explicit optional MCP function parameters.
[ ] Raw provider query/filter strings are not agent inputs.
[ ] Request/correlation IDs come from existing context and are not new agent inputs.
[ ] Existing auth, HTTP, timeout, retry, error, context, and redaction code is reused.
[ ] Total tool deadline is loaded from the active environment YAML.
[ ] The deadline covers retries and does not reset for each attempt.
[ ] Timeout cancels in-flight work and returns a retryable structured error.
[ ] The MCP client demonstrably receives every normalized tool failure.
[ ] Timeout and provider-failure messages reach the user through the unchanged UI schema.
[ ] Safe Account and Security Account populate the same parameter.
[ ] Invalid account suffixes fail locally without a provider call.
[ ] Tool schemas are inspected and tested.
[ ] Both tools pass mocked and nonproduction smoke tests.
[ ] Asset Services Agent passes end-to-end tests using only the two new tools.
[ ] Formatter Agent and final JSON/UI contract are unchanged.
[ ] Old generic tools remain available for rollback during this phase.
[ ] README and tool inventory are updated.
[ ] Completion report includes all evidence requested in Section 15.
```
