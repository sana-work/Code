# Octobot Current Architecture Problems and Code Fixes

**Document purpose:** isolate the problems in the current Octobot implementation and provide concrete, code-level remediation guidance.

**Prepared from:** supplied source-code screenshots, runtime traces, formatter-agent configuration screenshot, and the architecture discussion.

**Scope:** current implementation only. The full proposed architecture remains in `Octobot_Architecture_Design_Simplified.md`.

---

## 1. How to Use This Document

This document distinguishes three evidence levels:

| Label | Meaning |
|---|---|
| **Confirmed** | The file, line, or behavior is visible in a supplied screenshot or runtime trace. |
| **Trace-confirmed** | The runtime stack identifies the file and line, but the full source around that line was not supplied. |
| **Proposed** | New code or a new file recommended by this document. It is not claimed to exist today. |

Line numbers refer to the supplied code snapshot and can move after edits. Before changing the repository, find the named symbol as well as the line number.

```bash
rg -n "class ApplyFiltersRequest|def apply_filters|def _validate_request_schema|def get_service_schema" octobot_mcp
```

### 1.1 Filename clarification

The supplied runtime trace identifies:

```text
octobot_mcp/config/api_schema_registry.py:317
```

Some discussion referred to the same registry as:

```text
octobot_mcp/config/apigee_schema_registry.py
```

Only one should be treated as authoritative in the actual repository. Apply the registry fixes below to the file that contains `ServiceSchema`, `_SCHEMA_BY_NAME`, `_SCHEMA_BY_PORTABLE_ID`, and `get_service_schema()`. Do not create a second registry merely to match a filename used in the discussion.

---

## 2. Executive Problem Map

| ID | Severity | Current problem | Primary location | User-visible result |
|---|---:|---|---|---|
| P1 | Critical | A UUID or noncanonical name is used for local schema lookup | `services/apigee_service.py`, registry | `ValueError: Unknown service` |
| P2 | Critical | `service_name` is optional even though local validation depends on it | `models/apigee.py`, `tools/apigee_tools.py` | Unreliable fallback to portable ID |
| P3 | High | Discovery names and canonical registry names are inconsistent | schema registry | Valid service rejected locally |
| P4 | Critical | Invalid or unverified filter values can reach the provider | model, query parser, service | Provider `500`, including `sfacntnm=... SN` |
| P5 | High | Provider errors are flattened into a generic tool failure | HTTP client/service boundary | No actionable error; partial data lost |
| P6 | High | Retry behavior is not classified by failure type | HTTP client/service boundary | Duplicate expensive calls or avoidable failures |
| P7 | High | One generic tool asks the model to manage provider identifiers and syntax | `tools/apigee_tools.py` and specialist prompt | Wrong service, field, or filter selection |
| P8 | High | Current flow has no explicit multi-service execution result contract | agent/runtime boundary | One failure can hide successful service results |
| P9 | Medium | Formatter input is fragile markdown rather than typed data | formatter-agent configuration | Malformed or incomplete final output |
| P10 | Medium | Logs and metrics do not cleanly separate local validation from provider failures | service/tool middleware | Slow diagnosis and misleading alerts |
| P11 | Medium | README tool inventory does not match implemented tools | `README.md` | Operators test or document the wrong surface |
| P12 | High | Focused regression tests for the reported failures are missing or not evidenced | `tests/` | Same defects can reappear |

---

## 3. The Two Reported Failures Are Different

### 3.1 Failure A: local `Unknown service`

**Trace-confirmed path:**

```text
apply_filters
  -> octobot_mcp/services/apigee_service.py:272
     _validate_request_schema(request)
  -> octobot_mcp/services/apigee_service.py:215
     get_service_schema(...)
  -> octobot_mcp/config/api_schema_registry.py:317
     ValueError: Unknown service
```

This failure occurs before `_authorized_get()` and before the provider `/filter` endpoint is called. There is no downstream HTTP status for this path.

Known failing identifiers include:

```text
d3823c4c-88bf-4ad1-bafe-d99f527d36c8
view_api_octobot_events_entitlements
```

The registry reports only canonical names such as:

```text
view_cash_entitlements
view_events_entitlements
```

### 3.2 Failure B: provider `500`

**Trace-confirmed path:**

```text
POST /octobot/mcp                              -> 200
COIN authorization                            -> success
POST JWT/token endpoint                       -> 200
GET /api/services/{portable_id}/filter        -> 500
httpx.Response.raise_for_status()              -> HTTPStatusError
current wrapper                               -> ServiceUnavailableError
```

The failing URL contained:

```text
sfacntnm=4205640693%20SN
```

`%20` is a space, so the provider received:

```text
4205640693 SN
```

Later successful calls used numeric-only safe-account values. This is strong evidence for a filter-validation defect, but it is not absolute proof that the suffix is the only provider-side cause. The exact same request must be replayed with only the suffix removed.

### 3.3 Diagnostic decision rule

```text
Did the trace reach _authorized_get() or show a provider HTTP status?

No
  -> local request, schema, service-name, or metadata validation failure

Yes
  -> provider, authentication, rate-limit, transport, or provider-query failure
```

Do not diagnose these two paths as the same problem.

---

## 4. P1 - Mixed Identifier Types Cause `Unknown service`

### 4.1 Confirmed current behavior

The current validation is reported at `octobot_mcp/services/apigee_service.py:215` as effectively:

```python
schema = get_service_schema(
    request.service_name or request.service_portable_id
)
```

This expression treats two different identifiers as interchangeable:

| Identifier | Example | Correct purpose |
|---|---|---|
| Logical/canonical service name | `view_events_entitlements` | Select local validation schema |
| Discovery alias | `view_api_octobot_events_entitlements` | Normalize to canonical name |
| Portable ID | `d3823c4c-...` | Build the provider resource path |

When `service_name` is absent, Python passes the UUID to `get_service_schema()`. If the UUID is not in the static registry, the function raises `Unknown service`.

### 4.2 Why the logic is incorrect

The code uses one string parameter to represent three namespaces. The `or` operator selects the first nonempty value; it does not validate the identifier type or establish that the selected name and ID refer to the same service.

The local registry and provider route have separate responsibilities:

```text
canonical service name -> schema and validation contract
portable ID            -> /api/services/{portable_id}/filter
```

### 4.3 Immediate fix in the current architecture

**Edit:** `octobot_mcp/services/apigee_service.py`

**Current trace locations:** line 215 for schema lookup and line 272 for the validation call.

Replace the mixed lookup:

```python
schema = get_service_schema(
    request.service_name or request.service_portable_id
)
```

with an explicit name-only lookup:

```python
schema = get_service_schema(request.service_name)
```

This change requires the model and MCP tool fixes in Sections 5 and 6. Do not apply only this line if `service_name` can still be `None`.

### 4.4 Add an ID/name consistency check

The current architecture obtains both fields from discovery. Validate that the pair came from the same discovery result before querying the provider.

```python
@dataclass(frozen=True)
class DiscoveredService:
    service_name: str
    service_portable_id: str


def validate_service_pair(
    *,
    request_name: str,
    request_portable_id: str,
    discovered_services: Sequence[DiscoveredService],
) -> None:
    canonical_name = normalize_service_name(request_name)

    is_valid_pair = any(
        normalize_service_name(item.service_name) == canonical_name
        and item.service_portable_id == request_portable_id
        for item in discovered_services
    )

    if not is_valid_pair:
        raise RequestValidationError(
            code="SERVICE_ID_NAME_MISMATCH",
            message="The selected service name and portable ID do not match.",
            details={"service_name": canonical_name},
        )
```

Do not include the raw provider URL, token, or authorization data in the returned error.

### 4.5 Target-state resolution

When the service-specific tool migration is complete, the agent should not pass either a service name or portable ID. Each registered MCP tool represents one provider service. Shared tool code resolves that tool's metadata internally and validates the metadata row at startup.

---

## 5. P2 - `service_name` Is Optional but Required by the Design

### 5.1 Confirmed model lines

**File:** `octobot_mcp/models/apigee.py`

**Lines 14-30:** `ApplyFiltersRequest`

**Lines 17-20:** `service_portable_id` is required.

**Lines 22-29:** `service_name` is optional and says that the schema can be resolved from `service_portable_id`.

```python
service_name: str | None = Field(
    default=None,
    max_length=200,
    description=(
        "Optional service name (e.g. view_events_entitlements) used for schema "
        "validation. When omitted, the schema is resolved from "
        "service_portable_id."
    ),
)
```

### 5.2 Confirmed tool lines

**File:** `octobot_mcp/tools/apigee_tools.py`

**Lines 69-80:** current `apply_filters()` signature.

**Line 72:**

```python
service_name: str | None = None,
```

**Lines 89-93 and 98-102:** the tool documentation also calls `service_name` optional.

The dictionary tool contradicts this: at lines 44-47 it says `service_name` is required and has no default. The result is an inconsistent agent-facing contract.

### 5.3 Exact stabilization edits

#### Edit 1: request model

**File:** `octobot_mcp/models/apigee.py`

```python
service_name: str = Field(
    min_length=1,
    max_length=200,
    description=(
        "Service Name returned by get_filter_values. "
        "Used only to select the local validation schema."
    ),
)
```

#### Edit 2: MCP tool signature

**File:** `octobot_mcp/tools/apigee_tools.py`

```python
async def apply_filters(
    service_portable_id: str,
    service_name: str,
    select: list[str],
    filters: list[str] | None = None,
    query: str | None = None,
    range_from: str | None = None,
    range_to: str | None = None,
    skip: int = 0,
    take: int = 5000,
    skip_count: bool = True,
) -> dict[str, Any]:
```

The parameter order is deliberate: both identifiers are visible together. If callers invoke the function positionally, change all callers in the same commit or make construction keyword-only.

#### Edit 3: request construction

**File:** `octobot_mcp/tools/apigee_tools.py`

**Confirmed lines 123-134:** the request is constructed with named fields.

Retain the explicit assignment:

```python
request = ApplyFiltersRequest(
    service_portable_id=service_portable_id,
    service_name=service_name,
    select=select,
    filters=filters or [],
    query=query,
    range_from=range_from,
    range_to=range_to,
    skip=skip,
    take=take,
    skip_count=skip_count,
)
```

#### Edit 4: tool description

Replace every `service_name is OPTIONAL` statement with:

```text
service_name is REQUIRED in the current generic-tool workflow. Pass the exact
Name returned by get_filter_values. The local schema registry normalizes known
aliases. service_portable_id is used only for the provider route.
```

### 5.4 Acceptance tests

```python
def test_apply_filters_request_requires_service_name() -> None:
    with pytest.raises(ValidationError):
        ApplyFiltersRequest(
            service_portable_id="d3823c4c-88bf-4ad1-bafe-d99f527d36c8",
            select=["corp"],
        )
```

```python
async def test_tool_passes_both_service_identifiers(mocker) -> None:
    service = mocker.AsyncMock()
    tools = ApigeeTools(mcp_server=mocker.Mock(), service=service)

    # Invoke the registered function using the repository's test helper.
    # Assert the service receives a request with both fields populated.
```

---

## 6. P3 - Discovery Names Do Not Match Canonical Registry Names

### 6.1 Confirmed mismatch

Runtime input:

```text
view_api_octobot_events_entitlements
```

Known registry key:

```text
view_events_entitlements
```

The current registry also contains static portable IDs, including:

```text
c108015f-0605-4538-ba75-2d75316b8420
99d636d8-e83a-4ccc-9672-ee928dbf749c
```

The failing runtime UUID was:

```text
d3823c4c-88bf-4ad1-bafe-d99f527d36c8
```

### 6.2 Immediate registry fix

**Edit:** the existing schema registry file containing `get_service_schema()`.

Add a normalized alias map next to `_SCHEMA_BY_NAME`:

```python
_SERVICE_NAME_ALIASES: dict[str, str] = {
    "view_events_entitlements": "view_events_entitlements",
    "view_api_octobot_events_entitlements": "view_events_entitlements",
    "view_cash_entitlements": "view_cash_entitlements",
    "view_api_octobot_cash_entitlements": "view_cash_entitlements",
}


def normalize_service_name(service_name: str) -> str:
    normalized = service_name.strip().lower()
    return _SERVICE_NAME_ALIASES.get(normalized, normalized)
```

Change the normal schema lookup to name-only resolution:

```python
def get_service_schema(service_name: str) -> ServiceSchema:
    canonical_name = normalize_service_name(service_name)
    schema = _SCHEMA_BY_NAME.get(canonical_name)

    if schema is None:
        raise ValueError(
            f"Unknown service name: {service_name!r}. "
            f"Known canonical services: {sorted(_SCHEMA_BY_NAME)}"
        )

    return schema
```

### 6.3 Remove the ambiguous normal fallback

Current logic reportedly attempts:

```python
schema = _SCHEMA_BY_NAME.get(service_name)
if schema is None:
    schema = _SCHEMA_BY_PORTABLE_ID.get(service_name)
```

Remove `_SCHEMA_BY_PORTABLE_ID` from the normal validation path after `service_name` is mandatory. If compatibility is temporarily required, make it explicit:

```python
def get_service_schema_by_legacy_portable_id(
    service_portable_id: str,
) -> ServiceSchema:
    schema = _SCHEMA_BY_PORTABLE_ID.get(service_portable_id)
    if schema is None:
        raise ValueError(
            f"Unknown legacy portable ID: {service_portable_id!r}"
        )
    return schema
```

No new code should call this legacy function.

### 6.4 What not to do

Do not fix the current incident by replacing one hardcoded UUID with today's failing UUID:

```python
# Do not use this as the permanent fix.
service_portable_id = "d3823c4c-88bf-4ad1-bafe-d99f527d36c8"
```

That would only move provider metadata back into code and make the next service change require another deployment.

### 6.5 Tests

```python
@pytest.mark.parametrize(
    ("input_name", "expected_name"),
    [
        ("view_events_entitlements", "view_events_entitlements"),
        ("VIEW_EVENTS_ENTITLEMENTS", "view_events_entitlements"),
        (
            "view_api_octobot_events_entitlements",
            "view_events_entitlements",
        ),
        (
            "  view_api_octobot_events_entitlements  ",
            "view_events_entitlements",
        ),
    ],
)
def test_normalize_service_name(input_name: str, expected_name: str) -> None:
    assert normalize_service_name(input_name) == expected_name
```

```python
def test_unknown_name_does_not_fall_back_to_uuid() -> None:
    with pytest.raises(ValueError, match="Unknown service name"):
        get_service_schema("d3823c4c-88bf-4ad1-bafe-d99f527d36c8")
```

---

## 7. P4 - Filter Values Are Not Validated Strongly Enough

### 7.1 Confirmed source surface

**File:** `octobot_mcp/models/apigee.py`

**Lines 35-42:** `filters` accepts `list[str]` and documents a free-form `FIELD<op>VALUE` grammar.

**File:** `octobot_mcp/tools/apigee_tools.py`

**Lines 98-118:** the tool prompt teaches the model to construct the provider's filter syntax.

This makes the language model responsible for exact field names, operators, date syntax, list syntax, and provider-specific values.

### 7.2 Confirmed failing value

```text
sfacntnm=4205640693%20SN
```

The current stack allowed this value to reach the provider. The provider returned `500` rather than a useful validation response.

### 7.3 Immediate safe fix

Do not blindly remove `SN` in production code until the provider contract confirms that `sfacntnm` is always numeric. Reject invalid values locally and return a structured validation error.

**Edit:** `octobot_mcp/services/apigee_service.py` in `_validate_request_schema()` or a new validator called by it.

```python
def validate_filter_value(
    *,
    column: ColumnSchema,
    value: str,
) -> None:
    normalized = value.strip()

    if column.data_type == "int" and not normalized.isdigit():
        raise RequestValidationError(
            code="INVALID_FILTER_VALUE",
            message=(
                f"Filter {column.name!r} requires an integer value."
            ),
            details={
                "field": column.name,
                "expected_type": "int",
            },
        )
```

The validator should be metadata-driven. It must not contain a growing list of `if field == ...` rules for every provider column.

### 7.4 Replace ad hoc filter strings with a parser

For the stabilization patch, keep the public `list[str]` contract but parse it once into a typed internal object.

**Proposed file:** `octobot_mcp/services/filter_parser.py`

```python
from dataclasses import dataclass
from enum import StrEnum


class FilterOperator(StrEnum):
    EQ = "="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    CONTAINS = "%="


@dataclass(frozen=True)
class ParsedFilter:
    field: str
    operator: FilterOperator
    value: str
```

The parser must:

1. Match the longest operators first (`>=` before `>` and `!=` before `=`).
2. Reject empty field names and values unless `null` is explicitly valid.
3. Resolve aliases to exact source columns.
4. Validate the field exists for the selected service.
5. Validate the operator is permitted for the field's type.
6. Parse integer, decimal, date, timestamp, boolean, and list values.
7. Produce query parameters through `httpx` rather than string concatenation.

### 7.5 Construct the request using HTTP parameters

Avoid manually building `...?{query}` where possible.

```python
path = f"/api/services/{request.service_portable_id}/filter"
params = build_filter_params(request, schema)

response = await self._authorized_get(path, params=params)
```

The HTTP client should perform URL encoding. `build_filter_params()` should receive already validated values.

### 7.6 Required diagnostic replay

Before declaring the suffix as the only cause, replay these cases against a nonproduction provider environment:

| Case | `corp` | `sfacntnm` | Expected diagnostic value |
|---|---|---|---|
| 1 | `2026635491` | `4205640693 SN` | Reproduce current `500` |
| 2 | `2026635491` | `4205640693` | Isolate suffix effect |
| 3 | `2026635491` | omitted | Isolate account condition |
| 4 | omitted | `4205640693` | Isolate corp/account combination |

Record provider correlation IDs, status, and duration for each case. Do not record tokens or unmasked sensitive account data in general application logs.

### 7.7 Tests

```python
def test_integer_filter_rejects_suffix() -> None:
    with pytest.raises(RequestValidationError) as exc:
        validate_filter_value(
            column=ColumnSchema(name="sfacntnm", data_type="int"),
            value="4205640693 SN",
        )

    assert exc.value.code == "INVALID_FILTER_VALUE"
```

```python
def test_integer_filter_accepts_numeric_account() -> None:
    validate_filter_value(
        column=ColumnSchema(name="sfacntnm", data_type="int"),
        value="4205640693",
    )
```

---

## 8. P5 - Provider Errors Are Flattened into Generic Failures

### 8.1 Current behavior

The supplied trace shows `httpx.raise_for_status()` converting the downstream `500` to `HTTPStatusError`, after which the current boundary exposes a generic message such as:

```text
ServiceUnavailableError: Upstream service error
```

The UI may reduce this further to:

```text
Error occurred during MCP tool execution
```

This loses:

- whether the failure was local or downstream;
- downstream status classification;
- whether retry is safe;
- which service failed;
- provider correlation ID;
- whether other services succeeded.

### 8.2 Add a stable tool error contract

**Proposed file:** `octobot_mcp/models/tool_result.py`

```python
class ToolError(BaseModel):
    code: str
    category: Literal[
        "VALIDATION",
        "AUTHENTICATION",
        "AUTHORIZATION",
        "RATE_LIMIT",
        "UPSTREAM",
        "TRANSPORT",
        "INTERNAL",
    ]
    message: str
    retryable: bool
    service_name: str | None = None
    provider_status: int | None = None
    correlation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    data: list[dict[str, Any]] = Field(default_factory=list)
    pagination: dict[str, Any] | None = None
    error: ToolError | None = None
```

### 8.3 Classify HTTP failures deliberately

**Edit:** `octobot_mcp/services/apigee_service.py` or the shared authorized HTTP client used by it.

```python
def classify_provider_status(status_code: int) -> tuple[str, bool]:
    if status_code in {401, 403}:
        return "AUTHENTICATION", False
    if status_code == 429:
        return "RATE_LIMIT", True
    if status_code in {502, 503, 504}:
        return "UPSTREAM", True
    if status_code >= 500:
        return "UPSTREAM", False
    return "UPSTREAM", False
```

```python
try:
    response.raise_for_status()
except httpx.HTTPStatusError as exc:
    category, retryable = classify_provider_status(
        exc.response.status_code
    )

    correlation_id = exc.response.headers.get("x-correlation-id")
    logger.warning(
        "Provider request failed",
        extra={
            "service_name": request.service_name,
            "provider_status": exc.response.status_code,
            "retryable": retryable,
            "correlation_id": correlation_id,
        },
    )

    return ToolResult(
        status="FAILED",
        error=ToolError(
            code="PROVIDER_REQUEST_FAILED",
            category=category,
            message="The requested service could not return data.",
            retryable=retryable,
            service_name=request.service_name,
            provider_status=exc.response.status_code,
            correlation_id=correlation_id,
        ),
    ).model_dump()
```

### 8.4 Protected diagnostic logging

Provider response bodies can contain internal or sensitive information. If operations require the body for diagnosis:

- write only to the protected diagnostic sink;
- cap the size;
- redact credentials, account identifiers, cookies, and headers;
- do not return the body to the agent or user;
- attach a correlation ID to the safe tool error.

### 8.5 Tests

Test at least `400`, `401`, `403`, `429`, `500`, `502`, `503`, `504`, connect timeout, read timeout, and DNS/connect failure. Assert both `category` and `retryable`.

---

## 9. P6 - Retry and Timeout Behavior Needs Failure-Aware Rules

The traces show one explicit provider `500` after roughly 22 seconds and a successful call taking roughly 35 seconds. The failure was not a timeout.

### 9.1 Required rules

| Failure | Retry? | Reason |
|---|---:|---|
| Local validation error | No | The same request will fail again. |
| `400` / `404` / `422` | No | Request or resource issue. |
| `401` / `403` | No automatic retry after token refresh limit | Prevent auth loops. |
| `429` | Yes | Respect `Retry-After`. |
| `500` | No by default | May be deterministic query/data failure. |
| `502` / `503` / `504` | Yes, bounded | Usually transient gateway/provider failure. |
| Connect/read timeout | Yes, bounded | Transport may recover. |

### 9.2 Proposed retry policy

```python
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.5
```

Use exponential backoff with jitter and a total request deadline. Do not retry indefinitely and do not let each nested service consume the entire user-request deadline.

### 9.3 Metrics

Record:

```text
octobot_provider_request_duration_seconds{service, outcome}
octobot_provider_requests_total{service, status_class}
octobot_provider_retries_total{service, reason}
octobot_local_validation_failures_total{code}
```

Keep portable IDs and account values out of metric labels; they create high cardinality and may expose sensitive identifiers.

---

## 10. P7 - The Generic Tool Gives Too Much Provider Work to the Model

### 10.1 Confirmed current workflow

**File:** `octobot_mcp/tools/apigee_tools.py`

**Lines 24-35:** `get_filter_values()` discovers services.

**Lines 39-62:** `get_service_dictionary(service_name)` returns columns, required filters, default outputs, and aliases.

**Lines 69-135:** `apply_filters(...)` expects the model to pass:

- portable ID;
- service name;
- exact source columns;
- provider filter expressions;
- optional complex query syntax;
- ranges and pagination.

The model therefore participates in provider routing and query construction. This is the source of several current failure modes.

### 10.2 Stabilization change

Until the target migration is complete:

1. Make `service_name` mandatory.
2. Normalize names in code.
3. Validate the name/portable-ID pair from discovery.
4. Parse and type-check every filter.
5. Reject unknown columns locally.
6. Construct HTTP parameters in code.
7. Return structured errors.

The tool description should explain business intent and required inputs, but code must enforce every provider rule.

### 10.3 Target migration

Replace the generic public surface with one MCP tool per portable-ID service. The current five-tool target is:

```text
Asset Services specialist sub-agent
  -> AS service-specific tool 1
  -> AS service-specific tool 2

Transaction Management specialist sub-agent
  -> query_eod_security_transactions
  -> query_current_securities_transactions
  -> query_current_securities_transactions_with_settlement_instructions
```

The exact two AS names must come from the approved AS service metadata; do not invent them from the old entitlements examples if those services are being replaced.

All five thin wrappers live on one MCP server and share:

- metadata loading;
- column and filter validation;
- provider authentication;
- request construction;
- pagination;
- retry policy;
- error normalization;
- logging and metrics.

The specialist agent sees only its domain's tools. The public tool parameters contain business filters and output selections, not `service_name` or `service_portable_id`.

---

## 11. P8 - No Explicit Multi-Service Result Contract

A single user query can require multiple AS services, multiple TM services, or both domains. The current generic-tool flow does not define how multiple calls are planned, executed, correlated, or partially failed.

### 11.1 Required behavior

```text
User query
  -> Root selects AS, TM, or both
  -> Specialist selects one or more service-specific tools in its domain
  -> Independent calls run concurrently when there is no dependency
  -> Each call returns its own status and data
  -> Specialist returns one structured domain response
  -> Formatter receives all structured specialist responses
  -> Successful data is preserved when another service fails
```

### 11.2 Proposed service-call result

```python
class ServiceCallResult(BaseModel):
    tool_name: str
    status: Literal["SUCCESS", "FAILED", "NEEDS_CLARIFICATION"]
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[dict[str, Any]] = Field(default_factory=list)
    error: ToolError | None = None
```

### 11.3 Proposed specialist final response

```python
class SpecialistResult(BaseModel):
    domain: Literal["ASSET_SERVICES", "TRANSACTION_MANAGEMENT"]
    status: Literal[
        "SUCCESS",
        "PARTIAL_SUCCESS",
        "FAILED",
        "NEEDS_CLARIFICATION",
    ]
    intent: str
    service_results: list[ServiceCallResult]
```

### 11.4 Status aggregation

```python
def aggregate_status(
    results: Sequence[ServiceCallResult],
) -> str:
    statuses = {result.status for result in results}

    if statuses == {"SUCCESS"}:
        return "SUCCESS"
    if "SUCCESS" in statuses:
        return "PARTIAL_SUCCESS"
    if "NEEDS_CLARIFICATION" in statuses:
        return "NEEDS_CLARIFICATION"
    return "FAILED"
```

Do not stop all sibling calls because one provider request returns a nonretryable error. Cancel siblings only when the user request is cancelled, the total deadline expires, or a dependency makes the remaining calls invalid.

---

## 12. P9 - Formatter Input Is Fragile Markdown

### 12.1 Confirmed current contract

The supplied formatter-agent configuration screenshot shows `octobot_formatter_agent` receiving:

```text
{octobot_raw}
```

It parses markdown sections such as:

```text
### Intent
### Tools Used
### Data
### Key Attributes
### Missing Inputs
```

The prompt then converts these sections to the required final JSON.

### 12.2 Current problem

This contract depends on exact headings, valid markdown tables, stable header casing, and correctly escaped values. A specialist or intermediate LLM can omit or rename a section, produce a malformed table, or add prose that the formatter interprets incorrectly.

### 12.3 Where to fix it

This fix belongs in the formatter agent's stored configuration/prompt and in the application boundary that invokes it. It does not belong in the MCP tools repository.

The exact PostgreSQL table, row ID, and prompt line were not supplied, so no exact database location can be honestly cited. Locate the active formatter configuration by agent name:

```sql
SELECT *
FROM <agent_configuration_table>
WHERE agent_name = 'octobot_formatter_agent';
```

Replace `<agent_configuration_table>` with the actual table used by the runtime. Do not create a new table solely because this placeholder appears here.

### 12.4 Correct contract

Pass structured root and specialist responses directly to the formatter:

```json
{
  "userQuery": "...",
  "routingResult": {
    "domains": ["ASSET_SERVICES", "TRANSACTION_MANAGEMENT"]
  },
  "agentResults": [
    {
      "domain": "ASSET_SERVICES",
      "status": "SUCCESS",
      "serviceResults": []
    },
    {
      "domain": "TRANSACTION_MANAGEMENT",
      "status": "PARTIAL_SUCCESS",
      "serviceResults": []
    }
  ]
}
```

The formatter still owns all final presentation and must preserve the existing final output schema. Add schema validation after the formatter and one bounded repair attempt for invalid JSON.

---

## 13. P10 - Observability Does Not Separate Failure Stages

### 13.1 Required stage names

Add a stage to every structured log and trace span:

```text
request_received
service_discovery
service_resolution
request_validation
provider_authentication
provider_request
provider_response
specialist_aggregation
formatter
response_validation
```

### 13.2 Safe structured context

```python
logger.info(
    "Octobot service call completed",
    extra={
        "request_id": request_id,
        "stage": "provider_response",
        "service_name": request.service_name,
        "outcome": "failed",
        "provider_status": response.status_code,
        "duration_ms": duration_ms,
        "correlation_id": correlation_id,
    },
)
```

Do not put these in ordinary logs:

- JWTs or COIN authorization tokens;
- cookies or authorization headers;
- full provider URLs containing filters;
- unmasked account numbers;
- unrestricted provider response bodies.

### 13.3 Error-code ownership

| Error code | Owner | Provider call made? |
|---|---|---:|
| `UNKNOWN_SERVICE_NAME` | registry/service validation | No |
| `SERVICE_ID_NAME_MISMATCH` | discovery validation | No |
| `UNKNOWN_COLUMN` | schema validation | No |
| `INVALID_FILTER_VALUE` | typed filter validation | No |
| `PROVIDER_AUTH_FAILED` | provider adapter | Yes |
| `PROVIDER_RATE_LIMITED` | provider adapter | Yes |
| `PROVIDER_REQUEST_FAILED` | provider adapter | Yes |
| `PROVIDER_TIMEOUT` | provider adapter | Yes or attempted |
| `FORMATTER_OUTPUT_INVALID` | formatter boundary | Not applicable |

This table should drive alerts. `UNKNOWN_SERVICE_NAME` is an application defect or stale configuration alert; `PROVIDER_REQUEST_FAILED` is a provider/integration alert.

---

## 14. P11 - README and Runtime Tool Inventory Have Drifted

### 14.1 Confirmed documentation mismatch

The supplied `README.md` screenshot shows:

- lines 90-103: repository structure;
- lines 106-110: a Tools table containing only `octobot_dummy(message="hello")`.

The implementation screenshots clearly show `get_filter_values`, `get_service_dictionary`, and `apply_filters` registered in `octobot_mcp/tools/apigee_tools.py`.

### 14.2 Fix

**Edit:** `README.md` lines 106 onward.

Document the current MCP tools during stabilization, then replace the list with the five service-specific tools during migration.

Add a CI test that starts the MCP server, lists registered tools, and compares their names to a checked-in expected inventory. This catches missing registrations and stale documentation.

```python
def test_registered_tool_inventory(mcp_client) -> None:
    names = {tool.name for tool in mcp_client.list_tools()}
    assert names == EXPECTED_TOOL_NAMES
```

Avoid asserting full natural-language tool descriptions byte-for-byte; that makes harmless wording changes break CI. Validate required names and input-schema fields instead.

---

## 15. P12 - Required Regression Tests

The repository screenshot confirms a `tests/` directory, but the supplied evidence does not show tests covering the reported failures. Add focused tests under the existing test naming conventions.

### 15.1 Suggested test files

These filenames are proposed; align them with the repository's existing layout.

```text
tests/
  test_apigee_models.py
  test_api_schema_registry.py
  test_filter_parser.py
  test_apigee_service.py
  test_apigee_tools.py
  test_provider_error_mapping.py
  test_multi_service_aggregation.py
  test_formatter_contract.py
```

### 15.2 Minimum test matrix

| Test | Expected result |
|---|---|
| Missing `service_name` in current generic tool | Local validation error |
| Canonical service name | Correct schema |
| Known discovery alias | Correct canonical schema |
| Portable UUID passed as service name | Rejected locally |
| Name and portable ID from different discovery rows | `SERVICE_ID_NAME_MISMATCH` |
| Unknown selected column | Rejected before HTTP call |
| Missing required filter | Rejected before HTTP call |
| Integer filter with ` SN` suffix | Rejected before HTTP call |
| Numeric safe account | Accepted |
| Provider `429` | Retryable, respects `Retry-After` |
| Provider `500` | Structured nonretryable upstream error by default |
| Provider `503` | Bounded retry, then structured error |
| One of two service calls fails | `PARTIAL_SUCCESS`; successful rows retained |
| Formatter returns malformed JSON | One repair attempt, then controlled error |
| Registered tools | Exact approved inventory |

### 15.3 Assert that local failures do not call the provider

```python
async def test_invalid_service_does_not_call_provider(mocker) -> None:
    authorized_get = mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(),
    )

    result = await service.apply_filters(invalid_request)

    authorized_get.assert_not_awaited()
    assert result["error"]["code"] == "UNKNOWN_SERVICE_NAME"
```

This assertion is essential. It proves the boundary between local validation failures and provider failures.

---

## 16. File-by-File Change List

| File | Current lines/symbols | Required change |
|---|---|---|
| `octobot_mcp/models/apigee.py` | 14-30, `ApplyFiltersRequest` | Make `service_name` required during stabilization. |
| `octobot_mcp/models/apigee.py` | 35-42, `filters` | Retain temporarily, but parse into typed filters. |
| `octobot_mcp/tools/apigee_tools.py` | 24-35, `get_filter_values` | Return/validate a coherent name-ID pair. |
| `octobot_mcp/tools/apigee_tools.py` | 39-62, `get_service_dictionary` | Normalize aliases before lookup; keep exact column contract. |
| `octobot_mcp/tools/apigee_tools.py` | 69-135, `apply_filters` | Require `service_name`, correct docs, return structured errors. |
| `octobot_mcp/services/apigee_service.py` | trace line 215 | Resolve schema only from normalized `service_name`. |
| `octobot_mcp/services/apigee_service.py` | trace line 272 | Validate name-ID pair, columns, required filters, and values. |
| `octobot_mcp/services/apigee_service.py` | trace line 275 area | Use validated HTTP params; classify downstream errors. |
| schema registry | trace line 317, `get_service_schema` | Normalize aliases; remove ambiguous UUID fallback from normal path. |
| shared authorized HTTP client | symbol to locate | Add status classification, bounded retry, safe logging. |
| `README.md` | 90-110 | Correct architecture and tool inventory. |
| active formatter-agent config | exact table/row not supplied | Accept structured specialist results, not `{octobot_raw}` markdown. |
| `tests/` | existing directory confirmed | Add the regression matrix in Section 15. |

### 16.1 Locate the HTTP boundary

The exact `_authorized_get()` definition line was not supplied. Locate it with:

```bash
rg -n "def _authorized_get|async def _authorized_get|raise_for_status" octobot_mcp
```

Apply error normalization at the lowest shared provider boundary that still has service context. Do not duplicate the same `try/except` block in all five future tool wrappers.

---

## 17. Implementation Sequence

### Phase 1 - Reproduce and lock behavior with tests

1. Create tests for both exact failure paths.
2. Assert `Unknown service` never invokes the provider client.
3. Mock the provider `500` and assert the current generic error, then change the assertion as the fix is implemented.
4. Replay the safe-account suffix matrix in a nonproduction environment.

### Phase 2 - Stabilize current generic tools

1. Make `service_name` required in `ApplyFiltersRequest`.
2. Make it required in `apigee_tools.apply_filters()`.
3. Update the tool description so it no longer says optional.
4. Add canonical-name normalization and explicit aliases.
5. Resolve the schema only from the canonical name.
6. Validate the discovery name/portable-ID pair.
7. Parse filters and enforce dictionary data types.
8. Build HTTP query parameters from validated values.

Deploy these changes together. Deploying only the service lookup change while the tool can omit `service_name` creates a new `None` failure instead of fixing the contract.

### Phase 3 - Normalize errors and retries

1. Add `ToolError` and `ToolResult`.
2. Classify provider status codes.
3. Retry only approved transient failures.
4. Add request and provider correlation IDs.
5. Preserve safe provider diagnostics in protected logs.

### Phase 4 - Support multi-service results

1. Add `ServiceCallResult` and `SpecialistResult`.
2. Execute independent service calls concurrently with a total deadline.
3. Aggregate statuses without discarding successful data.
4. Test same-domain and cross-domain partial failures.

### Phase 5 - Migrate to five service-specific tools

1. Create one thin MCP wrapper per approved portable-ID service.
2. Keep shared runtime logic in common modules.
3. Remove service identifiers from public tool parameters.
4. Give each specialist sub-agent only its domain's tools.
5. Run old and new tool paths in shadow comparison if possible.
6. Retire `get_filter_values`, `get_service_dictionary`, and generic `apply_filters` after parity is proven.

### Phase 6 - Update the formatter boundary

1. Change the formatter prompt input from `{octobot_raw}` markdown to structured `routingResult` and `agentResults`.
2. Preserve the existing final response JSON contract.
3. Add final schema validation and one repair attempt.
4. Test no-data, clarification, success, partial success, and failure cases.

### Phase 7 - Documentation and release controls

1. Update `README.md` and runtime tool inventory.
2. Add migration and rollback notes.
3. Run unit, integration, MCP contract, and provider smoke tests.
4. Verify logs contain no tokens or raw sensitive filters.
5. Roll out gradually and monitor errors by stage and service.

---

## 18. Deployment and Rollback Plan

### 18.1 Stabilization release

Deploy the model, tool signature, registry normalization, service validation, and tests as one compatible release. Existing prompts or callers that invoke generic `apply_filters` must be updated at the same time because `service_name` becomes required.

### 18.2 Predeployment checks

```text
[ ] Every active generic-tool caller sends service_name.
[ ] Known discovery aliases have canonical mappings.
[ ] Name and portable ID are taken from one discovery record.
[ ] Invalid integer/date/timestamp filters fail locally.
[ ] Provider error categories pass unit tests.
[ ] Provider smoke tests succeed for each active service.
[ ] Logs redact tokens and sensitive values.
[ ] README and MCP inventory are current.
```

### 18.3 Runtime checks after deployment

```text
[ ] UNKNOWN_SERVICE_NAME count decreases to zero for approved services.
[ ] No increase in request-model validation failures from stale callers.
[ ] Provider 500s are visible separately from local validation failures.
[ ] No automatic retry storm on provider 500.
[ ] Successful sibling service data survives partial failures.
[ ] Formatter output continues to satisfy the final response schema.
```

### 18.4 Rollback

Keep the previous deployment artifact. If required callers cannot be updated atomically, introduce a short-lived compatibility period:

```python
service_name: str | None = None
```

but reject missing names with a controlled error before registry lookup:

```python
if not request.service_name:
    raise RequestValidationError(
        code="SERVICE_NAME_REQUIRED",
        message="The current generic tool requires service_name.",
    )
```

This is preferable to silently resolving the schema from a UUID. Remove the compatibility branch once all callers are updated.

---

## 19. Changes That Should Not Be Made for These Incidents

The supplied traces show successful MCP access, COIN authorization, JWT issuance, and successful provider requests in other cases. Do not change these merely to address `Unknown service` or the specific filter `500`:

```text
COIN configuration
JWT signing or verification
SSL certificates
MCP route
Apigee host or base route
Kubernetes/OpenShift service routing
global timeout alone
```

Also do not:

- add the current failing UUID blindly to a static registry;
- strip `SN` or other suffixes without confirming the provider contract;
- retry every `500` automatically;
- return raw provider bodies or stack traces to the formatter/user;
- put agent definitions in the MCP tools repository;
- ask every tool wrapper to reimplement authentication, validation, and retry logic.

---

## 20. Definition of Done

The current architecture is stabilized when all of the following are true:

1. A valid discovery alias resolves to one canonical schema name.
2. A portable ID is never used as the normal local schema key.
3. The current generic `apply_filters` requires both identifiers and validates that they match.
4. Unknown services, columns, missing filters, and invalid values fail before HTTP execution.
5. Provider failures return a stable structured category and retry decision.
6. A provider `500` does not appear as an unidentified MCP failure.
7. Multiple service calls can return `PARTIAL_SUCCESS` without losing successful data.
8. The formatter consumes structured specialist responses and preserves the approved final JSON schema.
9. MCP tool inventory documentation matches the running server.
10. Regression tests cover every reported failure and pass in CI.

---

## 21. Immediate Pull Request Breakdown

To keep review focused, use the following pull request sequence.

### PR 1 - Service resolution stabilization

```text
models/apigee.py
tools/apigee_tools.py
services/apigee_service.py
config/<actual schema registry filename>
tests for model, aliases, and no-provider-call validation
```

### PR 2 - Typed filters and query construction

```text
new shared filter parser/validator
service integration
integer/date/timestamp/operator tests
safe-account suffix regression test
```

### PR 3 - Error and retry contract

```text
ToolResult/ToolError models
shared HTTP classification
retry policy
logging/metrics
HTTP failure matrix tests
```

### PR 4 - Multi-service and formatter contract

```text
ServiceCallResult/SpecialistResult
parallel aggregation
partial success
formatter prompt/config update
final response schema tests
```

### PR 5 - Service-specific MCP tools

```text
five thin tool wrappers
shared service runtime
domain-scoped tool exposure
inventory and README update
old generic-tool deprecation
```

Do not combine unrelated refactoring with PR 1. The first release should be small enough that reviewers can verify the exact `Unknown service` call path and its tests.
