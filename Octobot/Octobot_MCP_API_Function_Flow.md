# Octobot MCP API and Function Flow

Date: 2026-09-06

Status: revised target implementation flow

## 1. Architecture decision

Octobot will not use PostgreSQL, a metadata repository, or a runtime metadata
loader for service definitions. All service-specific details are owned by the
MCP tools codebase and released with the MCP server.

Each of the five service-specific MCP tools exposes an explicit, typed function
signature. Required provider filters are required MCP parameters. Optional
filterable fields are optional MCP parameters. The parameter names,
descriptions, types, examples, and allowed values are visible to the agent in
the registered MCP tool schema.

Provider-only details remain internal to code:

- service portable ID;
- provider column names;
- business-name and alias mappings;
- default output columns;
- selectable and filterable column rules;
- required-filter rules;
- provider operator and data-type mappings;
- provider route and request construction.

The agent never constructs provider field names or raw filter expressions.

## 2. End-to-end summary

```text
MCP startup
  -> import five Python tool modules
  -> validate each code-defined tool contract
  -> register five explicit MCP function schemas
  -> server becomes ready

Each request
  User
  -> Root Agent
  -> AS or TM Specialist Sub-Agent
  -> inspect/select service-specific MCP tool
  -> populate explicit required and optional parameters
  -> code-defined tool wrapper
  -> shared service executor
  -> type and business-rule validation
  -> internal provider-field mapping
  -> provider request builder
  -> provider REST API
  -> response normalizer
  -> structured specialist response
  -> Formatter Agent
  -> final JSON validator
  -> User
```

There are no metadata database reads during startup or request processing.

## 3. Five service-specific tools

The MCP server registers exactly these target tools:

| Domain | Business service | Tool name |
| --- | --- | --- |
| Asset Services | Events Entitlements | `query_as_events_entitlements` |
| Asset Services | Cash Entitlements | `query_as_cash_entitlements` |
| Transaction Management | EOD Security Transactions | `query_tm_eod_security_transactions` |
| Transaction Management | Current Securities Transactions | `query_tm_current_securities_transactions` |
| Transaction Management | Current Securities Transactions with Settlement Instruction Details | `query_tm_current_securities_transactions_with_settlement_instruction_details` |

Each tool has its own explicit parameters. Do not expose one generic
`service_name + fields + raw filters` tool to the agent.

The exact required and optional parameters for each tool must be copied from the
approved provider contract and checked into the corresponding tool module. A
field that is required by one service does not automatically become required by
another service.

## 4. Agent-visible tool contract

### 4.1 Parameter rules

Each business input is a named function parameter:

- required provider filters have no default value;
- optional filters default to `None`;
- output selection uses an allowlisted enum or `Literal`, never provider text;
- constrained values use enums or `Literal` where the provider contract is
  stable;
- identifiers remain strings so leading zeroes are preserved;
- descriptions include accepted business terminology and concise examples;
- internal provider names and portable IDs are not included in descriptions.

For example, if Event ID and Safe Account are required by Events Entitlements,
both are required in the Python signature:

```python
from typing import Annotated

from pydantic import Field

RequestId = Annotated[
    str,
    Field(min_length=1, max_length=100, description="Request correlation ID."),
]

EventId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=40,
        description="Corporate-action Event ID supplied by the user.",
    ),
]

SafeAccount = Annotated[
    str,
    Field(
        pattern=r"^[0-9]+$",
        description=(
            "Safe Account or Security Account identifier. "
            "Preserve all digits, including leading zeroes."
        ),
    ),
]
```

### 4.2 Representative explicit tool

The following illustrates the target pattern. The final optional fields and
their types must match the verified Events Entitlements contract.

```python
@mcp_server.tool(tags={"AssetServices"})
async def query_as_events_entitlements(
    request_id: RequestId,
    event_id: EventId,
    safe_account: SafeAccount,
    event_category: str | None = None,
    option_type: str | None = None,
    payment_status: str | None = None,
    requested_fields: list[EventsEntitlementsField] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ToolResult:
    """Retrieve corporate-action event and entitlement details.

    Use this tool for event terms, options, key dates, deadlines, payment
    status, event status, and announcement details.

    Parameters:
        request_id: Request correlation ID.
        event_id: Required corporate-action Event ID.
        safe_account: Required Safe Account. "Security Account" is an accepted
            business synonym for this parameter.
        event_category: Optional event-category filter.
        option_type: Optional event-option filter.
        payment_status: Optional payment-status filter.
        requested_fields: Optional allowlisted output fields. When omitted,
            the tool uses its code-defined default output fields.
        limit: Maximum records to return, within the configured cap.
        offset: Zero-based record offset.
    """
    values = {
        "event_id": event_id,
        "safe_account": safe_account,
        "event_category": event_category,
        "option_type": option_type,
        "payment_status": payment_status,
    }
    return await service_runtime.execute(
        contract=EVENTS_ENTITLEMENTS_CONTRACT,
        request_id=request_id,
        values=values,
        requested_fields=requested_fields,
        limit=limit,
        offset=offset,
    )
```

The other four tools follow the same pattern but expose only their own verified
required and optional business fields.

### 4.3 Agent call

The Specialist Sub-Agent calls the tool with business parameters:

```json
{
  "request_id": "req-123",
  "event_id": "2026656277",
  "safe_account": "8001820000",
  "requested_fields": [
    "securityName",
    "eventType",
    "eventCategory",
    "paymentStatus"
  ],
  "limit": 100,
  "offset": 0
}
```

The agent does not send:

```text
service_name
service_portable_id
provider column names
provider URL
raw filter expressions
authentication information
```

## 5. Code-defined internal contract

Each tool module owns or imports one immutable internal contract. This contract
is not an external metadata source and is not supplied by the agent.

```python
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ValueType(StrEnum):
    STRING = "string"
    INTEGER_STRING = "integer_string"
    DECIMAL = "decimal"
    DATE = "date"
    TIMESTAMP = "timestamp"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class FieldContract:
    business_name: str
    provider_column: str
    value_type: ValueType
    required: bool = False
    selectable: bool = True
    filterable: bool = True
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolContract:
    tool_name: str
    domain: str
    portable_id: str
    fields: Mapping[str, FieldContract]
    default_output_fields: tuple[str, ...]
    maximum_limit: int
```

Representative Events Entitlements configuration:

```python
EVENTS_ENTITLEMENTS_CONTRACT = ToolContract(
    tool_name="query_as_events_entitlements",
    domain="ASSET_SERVICES",
    portable_id=EVENTS_ENTITLEMENTS_PORTABLE_ID,
    fields=MappingProxyType({
        "event_id": FieldContract(
            business_name="eventId",
            provider_column=VERIFIED_EVENT_ID_COLUMN,
            value_type=ValueType.INTEGER_STRING,
            required=True,
        ),
        "safe_account": FieldContract(
            business_name="safeAccount",
            provider_column=VERIFIED_SAFE_ACCOUNT_COLUMN,
            value_type=ValueType.INTEGER_STRING,
            required=True,
            aliases=(
                "safe account",
                "safe account number",
                "security account",
                "security account id",
            ),
        ),
        # Add every other verified selectable/filterable service field here.
    }),
    default_output_fields=VERIFIED_DEFAULT_OUTPUT_FIELDS,
    maximum_limit=500,
)
```

`VERIFIED_*` values above represent checked-in constants populated from the
approved provider contract during implementation. They are not runtime lookups.

## 6. Single source-of-truth rule

The explicit function signature is the agent-facing contract. The immutable
`ToolContract` is the provider-facing mapping. Because both use the same
business parameter keys, startup validation must reject drift between them.

For each tool, validate that:

1. every required `FieldContract` key is a required function parameter;
2. every optional filterable key is an optional function parameter;
3. every exposed business field exists in the internal contract;
4. every requested-field enum member resolves to one selectable field;
5. every default output field is selectable;
6. normalized aliases are unique within the tool;
7. the tool name and domain match the registered wrapper;
8. the portable ID is present and valid;
9. pagination defaults do not exceed the tool cap.

This comparison uses Python introspection during startup. It does not read an
external database.

## 7. MCP startup flow

Startup performs code registration and fail-fast validation only:

```text
start_mcp_server()
  -> import five tool modules
  -> collect code-defined ToolContract objects
  -> validate function signatures against ToolContract objects
  -> validate provider mappings, aliases, defaults, and limits
  -> register five MCP tools
  -> readiness = READY
```

Suggested implementation:

```python
def initialize_mcp_runtime() -> ServiceRuntime:
    contracts = (
        EVENTS_ENTITLEMENTS_CONTRACT,
        CASH_ENTITLEMENTS_CONTRACT,
        TM_EOD_SECURITY_TRANSACTIONS_CONTRACT,
        TM_CURRENT_SECURITIES_TRANSACTIONS_CONTRACT,
        TM_CURRENT_SECURITIES_WITH_SETTLEMENT_CONTRACT,
    )

    validate_contracts(contracts)

    return ServiceRuntime(
        provider_client=ProviderClient.from_environment(),
    )
```

The MCP server fails readiness when a tool signature, required parameter,
provider mapping, default output, alias, portable ID, or domain binding is
invalid.

## 8. Shared execution flow

Every service-specific wrapper calls the same runtime:

```text
ServiceRuntime.execute()
  -> validate contract identity
  -> validate required business parameters
  -> validate each value using its FieldContract
  -> validate requested output fields
  -> map business parameters to provider columns
  -> build provider request
  -> enforce configured total tool deadline
  -> provider client call and bounded retries within that deadline
  -> normalize response or error
  -> ToolResult
```

Suggested implementation:

```python
async def execute(
    self,
    *,
    contract: ToolContract,
    request_id: str,
    values: dict[str, object | None],
    requested_fields: list[str] | None,
    limit: int,
    offset: int,
) -> ToolResult:
    request = resolve_and_validate_request(
        contract=contract,
        values=values,
        requested_fields=requested_fields,
        limit=limit,
        offset=offset,
    )

    provider_request = build_provider_request(
        contract=contract,
        request=request,
    )

    try:
        provider_response = await self.provider_client.filter_service(
            portable_id=contract.portable_id,
            request_id=request_id,
            payload=provider_request,
        )
    except ProviderError as error:
        return normalize_provider_error(
            tool_name=contract.tool_name,
            request_id=request_id,
            error=error,
        )

    return normalize_provider_response(
        contract=contract,
        request_id=request_id,
        response=provider_response,
    )
```

The example is structural. The implementation must enforce the total deadline
at the shared runtime boundary and normalize deadline expiry rather than
allowing it to escape as an unhandled exception.

### 8.1 Configurable total tool deadline

The active environment YAML supplies the maximum wall-clock duration of one
tool invocation. Reuse the current YAML hierarchy and typed configuration
loader. If an equivalent setting does not exist, add one clearly named Asset
Services deadline setting to every supported environment YAML file. Do not
hard-code environment-specific timeout values in Python.

The deadline covers validation, provider calls, retry delays, retries, and
response normalization. All retries share the same remaining time; a retry
must not restart the deadline. When the deadline is crossed, cancel in-flight
provider work, perform no further retry, and return a normalized retryable
timeout result.

An HTTP connect/read timeout may remain separately configured. It protects an
individual network operation; the tool deadline limits the user's total wait.

## 9. Detailed request processing

For every tool call, the shared runtime performs these steps in order:

1. Verify that the wrapper supplied the expected code-defined contract.
2. Validate `request_id`, pagination, required parameters, and optional values.
3. Reject unknown inputs before making a provider request.
4. Validate each value against its declared type and constraints.
5. Preserve identifier strings exactly; never append labels or cast away
   leading zeroes.
6. Validate requested output fields against the tool's selectable allowlist.
7. Use code-defined default outputs when `requested_fields` is omitted.
8. Map business parameter names to internal provider columns.
9. Convert business operators and values to the provider contract.
10. Build the provider request from structured values.
11. Read the portable ID from the tool's internal code contract.
12. Call the provider through the shared client.
13. Apply HTTP timeout and bounded retry rules by error category, within the
    one configured total tool deadline.
14. Normalize the provider response or error.
15. Return the common `ToolResult` contract.

Raw provider filters are prohibited throughout this flow.

## 10. Safe Account and Security Account handling

`Safe Account`, `Safe Account Number`, `Security Account`, and
`Security Account ID` are accepted business expressions for the same
`safe_account` tool parameter where the service contract supports that field.

The MCP schema description makes the synonym visible to the agent. Once the
tool is called, the runtime receives only `safe_account` and maps it to the
verified provider column in the selected tool's internal contract.

Rules:

- preserve the supplied digits exactly;
- keep the value as a string;
- reject spaces or text suffixes inside the identifier;
- never append `SN` or another display label;
- do not apply this alias to a service that lacks the field;
- return `INVALID_FILTER_VALUE` locally and do not call the provider when the
  identifier violates its declared contract.

## 11. Provider REST API call

The shared provider client makes the request using internal code values:

```http
POST {PROVIDER_BASE_URL}/api/services/{portable_id}/filter
Authorization: Bearer {token}
X-Correlation-ID: req-123
Content-Type: application/json
```

Representative payload:

```json
{
  "columns": [
    "PROVIDER_SECURITY_NAME",
    "PROVIDER_EVENT_TYPE",
    "PROVIDER_PAYMENT_STATUS"
  ],
  "filters": [
    {
      "column": "PROVIDER_EVENT_ID",
      "operator": "EQ",
      "value": "2026656277"
    },
    {
      "column": "PROVIDER_SAFE_ACCOUNT",
      "operator": "EQ",
      "value": "8001820000"
    }
  ],
  "limit": 100,
  "offset": 0
}
```

The placeholder provider names above must be replaced with the exact verified
provider columns in code. The agent never sees or supplies them.

Provider base URL, authentication URLs, credentials, certificates, HTTP
timeouts, total tool deadline, and retry settings remain deployment
configuration. The total tool deadline is loaded from the active environment
YAML. Secrets must not be placed in tool contracts.

## 12. Response normalization

The provider response is converted into the existing common tool contract:

```json
{
  "requestId": "req-123",
  "toolName": "query_as_events_entitlements",
  "domain": "ASSET_SERVICES",
  "status": "SUCCESS",
  "tables": [
    {
      "name": "Events Entitlements",
      "columns": [
        "securityName",
        "eventType",
        "eventCategory",
        "paymentStatus"
      ],
      "rows": [
        {
          "securityName": "Example Security",
          "eventType": "DVCA",
          "eventCategory": "MAND",
          "paymentStatus": "Paid"
        }
      ]
    }
  ],
  "errors": []
}
```

Provider column names are translated back to business field names before the
result leaves the MCP server.

Possible tool statuses remain:

```text
SUCCESS
NO_DATA
ERROR
```

Errors contain a safe error code, tool name, retryability, and correlation ID.
Provider response bodies, credentials, internal URLs, and stack traces remain
outside the agent-visible result.

Expected failures must be returned over MCP in the existing structured result
shape; they must not exist only in logs. Provide safe text content as a
fallback when required by the deployed MCP client. For an overall tool
deadline, use the repository's existing stable timeout code or `TOOL_TIMEOUT`
when none exists, set `retryable` to `true`, and use this user-facing message:

```text
The request took longer than the configured time limit. Please try again.
```

The propagation path is:

```text
deadline or provider failure
  -> normalized ToolResult with safe code/message/retryability/correlation ID
  -> Specialist Agent treats the error as the result for the current turn
  -> Formatter maps it into the existing final failed-response JSON
  -> UI displays the safe message without a data table
```

This behavior does not change the final production JSON schema. The agent must
not invent data, claim success, or silently discard the error. Technical error
details remain in redacted server logs associated with the same correlation
ID.

## 13. Multiple-service queries

The Specialist Sub-Agent can select more than one service-specific tool when a
request genuinely spans services.

Independent calls may run in parallel:

```python
first_result, second_result = await asyncio.gather(
    call_first_tool(),
    call_second_tool(),
)
```

Dependent calls run sequentially only when one tool returns a documented
business identifier required by the next tool.

Cross-service orchestration belongs to the Specialist Sub-Agent. It does not
belong in the shared MCP runtime.

If one call succeeds and another fails, preserve the successful result and
return a structured partial status.

## 14. Final response flow

```text
ToolResult[]
  -> Specialist Sub-Agent creates SpecialistResponse
  -> Formatter Agent receives AS/TM SpecialistResponse objects
  -> Formatter builds final tables, attributes, toolsUsed, and status
  -> Final JSON Validator validates the production schema
  -> validated response returns to the User
```

The Formatter Agent remains outside the MCP server and has no MCP tools or
provider access. The production final JSON schema and UI table-placeholder
contract are unchanged by this architecture revision.

## 15. Proposed MCP module structure

```text
octobot-mcp/
  server.py
  startup.py
  contracts/
    common.py
    as_events_entitlements.py
    as_cash_entitlements.py
    tm_eod_security_transactions.py
    tm_current_securities_transactions.py
    tm_current_securities_with_settlement.py
    tool_result.py
    tool_error.py
  tools/
    as_events_entitlements.py
    as_cash_entitlements.py
    tm_eod_security_transactions.py
    tm_current_securities_transactions.py
    tm_current_securities_with_settlement.py
  runtime/
    service_runtime.py
    contract_validator.py
    request_validator.py
    provider_request_builder.py
    response_normalizer.py
    error_normalizer.py
  providers/
    provider_client.py
    authentication.py
  tests/
    test_registered_tool_schemas.py
    test_contract_validation.py
    test_request_validation.py
    test_provider_request_builder.py
    test_response_normalizer.py
```

There is no `metadata/service_repository.py`, database migration, metadata SQL,
or startup database client in the target structure.

## 16. Responsibility summary

| Layer | Responsibility |
| --- | --- |
| Root Agent | Route the user request to AS, TM, both domains, clarification, or out of scope |
| Specialist Sub-Agent | Select the smallest sufficient domain tool set and populate explicit business parameters |
| Service-specific MCP function | Expose required and optional typed parameters with business descriptions |
| Code-defined `ToolContract` | Own portable ID, provider mapping, aliases, defaults, field capabilities, and limits |
| Startup contract validator | Detect drift between Python signatures and internal contracts before readiness |
| Shared service runtime | Validate values, build provider requests, invoke the provider, and normalize results |
| Provider client | Own HTTP transport, authentication, TLS, timeout, and retry behavior |
| Specialist response | Preserve normalized service results and partial failures |
| Formatter Agent | Build the existing final tables, attributes, answer, and status |
| Final JSON validator | Enforce the unchanged production response schema |

## 17. Required tests

### 17.1 MCP schema tests

For every registered tool, inspect the generated MCP JSON Schema and assert:

- the expected required parameters are listed in `required`;
- optional filter parameters are present but not required;
- parameter descriptions contain approved business terminology;
- identifier patterns and length constraints are present;
- output-selection values are allowlisted;
- provider column names and portable IDs are absent.

### 17.2 Contract tests

Assert that:

- all five tools have exactly one internal contract;
- function parameters and contract keys match;
- aliases resolve unambiguously within one tool;
- required fields cannot be omitted;
- invalid numeric/date/timestamp values fail locally;
- invalid output fields fail locally;
- no local validation failure invokes the provider;
- business fields map to the exact verified provider columns;
- default outputs are valid selectable fields.

### 17.3 Account synonym tests

Prompt-level tests should show that all approved user phrases populate the same
`safe_account` parameter. Runtime tests should prove that each call generates
the same provider condition and preserves the identifier:

```text
Safe Account 8001820000
Safe Account Number 8001820000
Security Account 8001820000
Security Account ID 8001820000
```

Expected internal outcome:

```text
business parameter = safe_account
provider column = verified code-defined account column
provider value = "8001820000"
```

### 17.4 Error tests

Test local validation, `400`, `401`, `403`, `404`, `429`, `500`, `502`, `503`,
`504`, connection failure, and timeout. Verify stable error categories and
bounded retry behavior. A `429` must respect `Retry-After`; invalid input and
nonretryable provider rejections must not be retried.

Also test the total tool deadline with a deterministic slow provider. Verify
that each environment YAML value is loaded correctly, retries share one
deadline, in-flight work is cancelled, the MCP client receives the structured
timeout, and the unchanged Formatter/UI response contains the try-again
message and no table. Invalid deadline configuration must fail according to
the repository's existing startup configuration policy.

## 18. Code-contract change process

Service-contract changes follow the normal code delivery lifecycle:

```text
update the affected tool signature and ToolContract
  -> update schema, mapping, and regression tests
  -> peer review
  -> CI validation
  -> deploy the MCP server
  -> rolling restart of MCP replicas
  -> smoke-test the changed tool
```

Contract changes are atomic with the deployed code version. Replicas must not
mix tool signatures from one version with internal mappings from another.

## 19. Acceptance criteria

The revised architecture is complete when:

1. no PostgreSQL or external metadata dependency exists in the MCP startup or
   request path;
2. exactly five service-specific tools are registered;
3. every provider-required filter is a required MCP parameter;
4. every supported optional filter is an explicit optional parameter;
5. the agent can inspect parameter names, types, descriptions, and constraints;
6. the agent cannot supply portable IDs, provider columns, routes, or raw
   filter expressions;
7. startup validation detects signature-to-contract drift;
8. all provider requests are built deterministically by shared code;
9. provider responses are normalized to business field names;
10. specialist partial-success behavior is preserved;
11. the Formatter Agent and final production JSON schema remain unchanged;
12. all schema, contract, provider, error, and synonym tests pass.
