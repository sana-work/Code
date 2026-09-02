# Octobot Backend Stabilization Fix

## 1. Confirmed Root Causes

The supplied source and production screenshots confirm four separate defects.

1. `get_filter_values()` returns the upstream discovery response unchanged, but
   `_SCHEMA_BY_NAME` contains only two service dictionaries. A service can
   therefore be advertised to the agent and then fail in
   `get_service_dictionary()` with `ValueError: Unknown service name`.
2. `ColumnSchema` has one broad `allowed_columns` concept. The backend therefore
   treats filter-only fields as valid `$select` projections, and may include
   fields the provider rejects in a default projection.
3. `apply_filters()` catches only the local `InvalidParamsError`. Exceptions
   from `_authorized_get()` occur after that catch and escape as generic FastMCP
   tool-execution failures.
4. The HTTP exception decorators use `raise ... from exc`. The chained
   `httpx.HTTPStatusError` includes the complete request URL and query values.
   `httpx` INFO logging can expose the same URL independently.

There is also a concrete implementation mismatch in the current error handler:
`CitiMCPToolError` stores structured information in `exc.details`, while
`apply_filters()` reads `getattr(exc, "data", None)`. That loses the error code
and details even for locally handled failures.

## 2. Files and Locations

| Order | File | Current symbol | Required change |
|---|---|---|---|
| 1 | `octobot_mcp/config/apigee_schema_registry.py` | `ColumnSchema` | Add `is_output_column` at the end |
| 2 | Same file | `ServiceSchema` | Add `selectable_columns` and contract checks |
| 3 | Same file | affected column declarations | Mark provider-rejected projections as non-output after dictionary verification |
| 4 | Same file | registry helpers | Add `supports_service_schema()` |
| 5 | `octobot_mcp/services/apigee_service.py` | `get_filter_values()` | Return only services with registered schemas |
| 6 | Same file | `get_service_dictionary()` | Return selectable metadata and a structured unknown-service error |
| 7 | Same file | `_suggest_columns()` | Suggest from the correct capability set |
| 8 | Same file | `_validate_request_schema()` | Validate `select` and filters against different sets |
| 9 | Same file | `apply_filters()` | Catch all expected `CitiMCPToolError` failures around the provider call |
| 10 | `octobot_mcp/utils/exceptions.py` | `_map_httpx_error()` and decorators | Add safe metadata and suppress chaining |
| 11 | `octobot_mcp/logconfig.yaml` | `loggers` | Suppress `httpx` and `httpcore` INFO request logs |
| 12 | `octobot_mcp/config/log_filters.py` | existing filters | Add defense-in-depth redaction |
| 13 | `octobot_mcp/tools/apigee_tools.py` | tool docstrings | Explain selectable versus filter-only fields |
| 14 | `tests/` | regression tests | Lock discovery, validation, errors, and logging |

Function and class names are authoritative because line numbers can shift.

## 3. Schema Registry

### 3.1 Preserve existing constructors

The current declarations pass all six existing `ColumnSchema` values
positionally. Add the new field **last**, with a default, so every existing
declaration remains valid:

```python
@dataclass(frozen=True)
class ColumnSchema:
    """A single column in the Data-on-Demand dictionary."""

    name: str
    english_name: str
    description: str
    data_type: str
    is_required_filter: bool
    is_default_output: bool
    is_output_column: bool = True
```

Do not insert the flag before either existing boolean. Doing that would silently
reinterpret every positional declaration.

### 3.2 Add selectable columns and fail-fast checks

Add these members to `ServiceSchema`:

```python
@dataclass(frozen=True)
class ServiceSchema:
    service_portable_id: str
    service_name: str
    english_name: str
    columns: tuple[ColumnSchema, ...]
    aliases: dict[str, str]

    def __post_init__(self) -> None:
        names_lower = [column.name.lower() for column in self.columns]
        duplicates = sorted({
            name
            for name in names_lower
            if names_lower.count(name) > 1
        })
        if duplicates:
            raise ValueError(
                f"Duplicate column names for {self.service_name}: "
                f"{duplicates}"
            )

        invalid_defaults = sorted(
            column.name
            for column in self.columns
            if column.is_default_output and not column.is_output_column
        )
        if invalid_defaults:
            raise ValueError(
                f"Default output columns must be selectable for "
                f"{self.service_name}: {invalid_defaults}"
            )

        known_names = set(names_lower)
        invalid_aliases = sorted(
            alias
            for alias, target in self.aliases.items()
            if target.lower() not in known_names
        )
        if invalid_aliases:
            raise ValueError(
                f"Aliases target unknown columns for "
                f"{self.service_name}: {invalid_aliases}"
            )

    @property
    def allowed_columns(self) -> frozenset[str]:
        return frozenset(column.name for column in self.columns)

    @property
    def selectable_columns(self) -> frozenset[str]:
        return frozenset(
            column.name
            for column in self.columns
            if column.is_output_column
        )

    @property
    def required_filter_columns(self) -> frozenset[str]:
        return frozenset(
            column.name
            for column in self.columns
            if column.is_required_filter
        )

    @property
    def default_output_columns(self) -> tuple[str, ...]:
        return tuple(
            column.name
            for column in self.columns
            if column.is_default_output
        )
```

`__post_init__()` is preferable to a validation method that callers must
remember to invoke. Every schema is checked when the module constructs it.

### 3.3 Correct the affected metadata

The provider rejected three projected fields in the captured request. Verify
their exact capabilities against the provider dictionary for that service.
For each field that may be used as a filter but not returned in `$select`, keep
its existing flags and append `False`:

```python
ColumnSchema(
    "provider_exact_name",
    "Human label",
    "Description",
    "string",
    True,   # required filter
    False,  # default output
    False,  # output column
)
```

For an optional filter-only field, the last three arguments are:

```python
False, False, False
```

Do not mark a field non-output solely from its business meaning. Confirm the
current provider dictionary first. If a rejected field is obsolete rather than
filter-only, remove or rename its registry entry to match the provider.

The registry must satisfy these invariants:

```text
default_output_columns is a subset of selectable_columns
required_filter_columns may include non-selectable columns
aliases resolve to real columns
column source names match the provider exactly
```

### 3.4 Expose registry support safely

Add a non-throwing helper near `get_service_schema()`:

```python
def supports_service_schema(service_name: str) -> bool:
    canonical_name = normalize_service_name(service_name)
    return canonical_name in _SCHEMA_BY_NAME
```

Export this helper only if the package uses explicit exports.

## 4. Discovery Must Match the Registry

### 4.1 Why this is required

`get_filter_values()` currently returns `response.json()` directly. Discovery
can therefore list services for which `get_service_dictionary()` is guaranteed
to fail. The agent is following the discovery tool correctly; the two backend
tools expose inconsistent contracts.

### 4.2 Recommended behavior

Keep the upstream discovery call because it supplies environment-specific
portable IDs. Before returning the payload, filter its service entries by
`supports_service_schema(entry[<name field>])`. Preserve each accepted upstream
entry unchanged so its current portable ID remains authoritative.

Conceptually:

```python
payload = response.json()
services = payload[DISCOVERY_ITEMS_KEY]
payload[DISCOVERY_ITEMS_KEY] = [
    service
    for service in services
    if supports_service_schema(service[DISCOVERY_NAME_KEY])
]
```

After filtering, update any count field that describes this returned collection.
Do not leave a total claiming more selectable services than the response holds.

The exact JSON field names are not visible in the screenshots. Use the actual
provider response rather than guessing `items` versus `Items`, or `name` versus
`Name`.

If all upstream services are intended to be usable, the alternative is to add a
complete `ServiceSchema` for every discovered service. Do not alias an unrelated
service to one of the two entitlement schemas.

## 5. Structured Service Errors

### 5.1 Import the base tool exception

In `apigee_service.py`, include `CitiMCPToolError` in the existing exception
imports:

```python
from octobot_mcp.utils.exceptions import (
    CitiMCPToolError,
    InvalidParamsError,
    ServiceUnavailableError,
    network_error_handler_async,
)
```

Keep any other existing imports.

### 5.2 Add one result builder

Add this helper inside `ApigeeService`:

```python
_RETRYABLE_CODES = frozenset({
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
    "TIMEOUT",
    "UPSTREAM_RATE_LIMITED",
    "UPSTREAM_UNAVAILABLE",
    "UPSTREAM_TIMEOUT",
})

_SAFE_DETAIL_KEYS = frozenset({
    "provider_status",
    "service_name",
    "invalid_select_columns",
    "invalid_filter_columns",
    "suggested_columns",
    "selectable_columns",
    "allowed_columns",
    "missing_fields",
})

@classmethod
def _error_result(
    cls,
    exc: CitiMCPToolError,
    *,
    include_records: bool,
) -> dict[str, Any]:
    source_details = (
        exc.details if isinstance(exc.details, dict) else {}
    )
    code = str(
        source_details.get("error_code")
        or exc.app_error_code
    )
    retryable = bool(
        source_details.get(
            "retryable",
            code in cls._RETRYABLE_CODES,
        )
    )
    details = {
        key: value
        for key, value in source_details.items()
        if key in cls._SAFE_DETAIL_KEYS
    }
    result: dict[str, Any] = {
        "status": (
            "NEEDS_CLARIFICATION"
            if code == "MISSING_REQUIRED_FILTER"
            else "ERROR"
        ),
        "error": {
            "code": code,
            "message": exc.message,
            "retryable": retryable,
            "details": details,
        },
    }
    if include_records:
        result["records"] = []
    return result
```

This deliberately reads `exc.details`. Replace the current
`getattr(exc, "data", None)` logic.

Never add request URLs, query text, filter values, authorization headers,
provider response bodies, portable IDs, or stack traces to `details`.

### 5.3 Normalize unknown dictionary requests

Update `get_service_dictionary()`:

```python
def get_service_dictionary(
    self,
    service_name: str,
) -> dict[str, Any]:
    try:
        schema = get_service_schema(service_name)
    except ValueError:
        error = InvalidParamsError(
            "The selected service is not supported.",
            {
                "error_code": "UNKNOWN_SERVICE_NAME",
                "service_name": service_name,
            },
        )
        return self._error_result(
            error,
            include_records=False,
        )

    return {
        "required_filter_columns": sorted(
            schema.required_filter_columns
        ),
        "default_output_columns": list(
            schema.default_output_columns
        ),
        "selectable_columns": sorted(
            schema.selectable_columns
        ),
        "columns": [
            {
                "name": column.name,
                "english_name": column.english_name,
                "description": column.description,
                "data_type": column.data_type,
                "is_required_filter": column.is_required_filter,
                "is_default_output": column.is_default_output,
                "is_output_column": column.is_output_column,
            }
            for column in schema.columns
        ],
        "aliases": schema.aliases,
        "service_portable_id": schema.service_portable_id,
        "service_name": schema.service_name,
    }
```

The portable ID remains available to the tool workflow, but it must not be
shown in the final user-facing answer or ordinary logs.

## 6. Capability-Aware Suggestions and Validation

### 6.1 Restrict suggestions to the relevant set

The current `_suggest_columns()` searches `schema.allowed_columns`, so an
invalid output field can be corrected to another filter-only field. Change its
signature to accept candidates:

```python
@staticmethod
def _suggest_columns(
    invalid_columns: list[str],
    schema: ServiceSchema,
    candidate_columns: frozenset[str],
) -> dict[str, str]:
    lower_to_canonical = {
        column.lower(): column
        for column in candidate_columns
    }
    allowed_lower = sorted(lower_to_canonical)
    suggestions: dict[str, str] = {}

    for column in invalid_columns:
        normalized = column.strip().lower()
        alias_target = schema.aliases.get(normalized)
        if (
            alias_target is not None
            and alias_target.lower() in lower_to_canonical
        ):
            suggestions[column] = lower_to_canonical[
                alias_target.lower()
            ]
            continue

        close = difflib.get_close_matches(
            normalized,
            allowed_lower,
            n=1,
            cutoff=0.7,
        )
        if close:
            suggestions[column] = lower_to_canonical[close[0]]

    return suggestions
```

### 6.2 Validate `$select` against selectable columns

In `_validate_request_schema()`, replace the shared set used for select
validation with:

```python
# Selectable and filterable columns have different rules.
selectable_lower = frozenset(
    column.lower() for column in schema.selectable_columns
)
selectable_columns = sorted(schema.selectable_columns)

filterable_lower = frozenset(
    column.lower() for column in schema.allowed_columns
)
filterable_columns = sorted(schema.allowed_columns)

invalid_select = sorted({
    column
    for column in request.select
    if column.strip().lower() not in selectable_lower
})

if invalid_select:
    raise InvalidParamsError(
        "Invalid select columns for service",
        {
            "error_code": "INVALID_SELECT_COLUMNS",
            "service_name": schema.service_name,
            "invalid_select_columns": invalid_select,
            "suggested_columns": self._suggest_columns(
                invalid_select,
                schema,
                schema.selectable_columns,
            ),
            "selectable_columns": selectable_columns,
        },
    )

filter_fields = {
    field
    for field in (
        self._extract_filter_field(expression)
        for expression in request.filters
    )
    if field
}

invalid_filter_fields = sorted({
    field
    for field in filter_fields
    if field not in filterable_lower
})

if invalid_filter_fields:
    raise InvalidParamsError(
        "Invalid filter columns for service",
        {
            "error_code": "INVALID_FILTER_COLUMNS",
            "service_name": schema.service_name,
            "invalid_filter_columns": invalid_filter_fields,
            "suggested_columns": self._suggest_columns(
                invalid_filter_fields,
                schema,
                schema.allowed_columns,
            ),
            "allowed_columns": filterable_columns,
        },
    )
```

Do not include `service_portable_id` in this error.

### 6.3 Keep filter validation broader

Continue validating filter fields against all known columns until the provider
metadata supplies a separate optional-filter capability:

```python
filterable_lower = frozenset(
    column.lower()
    for column in schema.allowed_columns
)

invalid_filter_fields = sorted({
    field
    for field in filter_fields
    if field not in filterable_lower
})

if invalid_filter_fields:
    raise InvalidParamsError(
        "Invalid filter columns for service",
        {
            "error_code": "INVALID_FILTER_COLUMNS",
            "service_name": schema.service_name,
            "invalid_filter_columns": invalid_filter_fields,
            "suggested_columns": self._suggest_columns(
                invalid_filter_fields,
                schema,
                schema.allowed_columns,
            ),
            "allowed_columns": sorted(
                schema.allowed_columns
            ),
        },
    )
```

Required-filter checking remains unchanged except that its error details should
not contain the portable ID.

## 7. Normalize Provider Failures in `apply_filters()`

The current try/except ends before query construction and
`await self._authorized_get(url)`. Replace that narrow handler with one that
covers validation and the provider call:

```python
@time_logger_async("Apigee apply filters")
async def apply_filters(
    self,
    request: ApplyFiltersRequest,
) -> dict[str, Any]:
    try:
        self._validate_request_schema(request)

        query = self._build_filter_query(request)
        url = (
            f"{self._apigee.data_base_url}/api/services/"
            f"{request.service_portable_id}/filter?{query}"
        )
        response = await self._authorized_get(url)
    except CitiMCPToolError as exc:
        return self._error_result(
            exc,
            include_records=True,
        )

    logger.info(
        "apply_filters upstream ids: "
        "X-DoD-Request-ID=%s X-Request-ID=%s",
        _sanitize_log_value(
            response.headers.get("X-DoD-Request-ID", "-")
        ),
        _sanitize_log_value(
            response.headers.get("X-Request-ID", "-")
        ),
    )
    payload = response.json()
    payload["pagination"] = {
        "page_number": response.headers.get(
            "X-Paging-PageNumber"
        ),
        "total_page_count": response.headers.get(
            "X-Paging-TotalPageCount"
        ),
        "total_record_count": response.headers.get(
            "X-Paging-TotalRecordCount"
        ),
    }
    return payload
```

The important change is the exception boundary, not a rewrite of query syntax.
The current builder intentionally preserves provider operators, so changing it
to generic `httpx` parameters should be a separate compatibility-tested change.

Catch `CitiMCPToolError`, not `Exception`. Programming defects should remain
visible to operations.

## 8. Safe HTTP Exception Mapping

### 8.1 Add safe error metadata

Modify `_map_httpx_error()` so expected failures carry only status and retry
information:

```python
def _map_httpx_error(exc: httpx.HTTPError) -> CitiMCPToolError:
    if isinstance(exc, httpx.TimeoutException):
        return TimeoutError(
            "Upstream request timed out",
            {
                "error_code": "UPSTREAM_TIMEOUT",
                "retryable": True,
            },
        )

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code

        if status == 429:
            return RateLimitError(
                "Upstream rate limit reached",
                {
                    "error_code": "UPSTREAM_RATE_LIMITED",
                    "provider_status": status,
                    "retryable": True,
                },
            )
        if status in (401, 403):
            return PermissionDeniedError(
                "Upstream rejected authorization",
                {
                    "error_code": "UPSTREAM_PERMISSION_DENIED",
                    "provider_status": status,
                    "retryable": False,
                },
            )
        if status == 404:
            return NotFoundError(
                "Upstream resource not found",
                {
                    "error_code": "UPSTREAM_NOT_FOUND",
                    "provider_status": status,
                    "retryable": False,
                },
            )
        if 400 <= status < 500:
            return InvalidParamsError(
                "Upstream rejected the request",
                {
                    "error_code": "UPSTREAM_REQUEST_REJECTED",
                    "provider_status": status,
                    "retryable": False,
                },
            )
        return ServiceUnavailableError(
            "Upstream service error",
            {
                "error_code": "UPSTREAM_UNAVAILABLE",
                "provider_status": status,
                "retryable": True,
            },
        )

    return ServiceUnavailableError(
        "Upstream service is unavailable",
        {
            "error_code": "UPSTREAM_UNAVAILABLE",
            "retryable": True,
        },
    )
```

Do not include `str(exc)`, `exc.request.url`, request headers, or response text.

### 8.2 Suppress the original exception context

Make the same one-line change in both decorators:

```python
except httpx.HTTPError as exc:
    raise _map_httpx_error(exc) from None
```

This is the key traceback redaction fix. `raise ... from exc` explicitly exposes
the original `httpx` error, whose message contains the complete URL.

## 9. Logging Configuration

### 9.1 Disable HTTP client request logs

Merge these entries into the existing `loggers:` mapping in
`octobot_mcp/logconfig.yaml`:

```yaml
loggers:
  httpx:
    level: WARNING
    handlers: [console]
    propagate: false
  httpcore:
    level: WARNING
    handlers: [console]
    propagate: false
```

Do not create a second top-level `loggers` key. Keep the existing `uvicorn`
entries.

### 9.2 Add defense-in-depth redaction

Append a filter compatible with the existing filters in
`octobot_mcp/config/log_filters.py`:

```python
import logging
import re


class SensitiveDataFilter(logging.Filter):
    _patterns = (
        re.compile(
            r"(?i)(authorization|cookie|token|client_secret)"
            r"\s*[:=]\s*[^\s,;&]+"
        ),
        re.compile(
            r"(?i)(account|event|corp|sfacntnm)"
            r"\s*[:=]\s*[^\s,;&]+"
        ),
        re.compile(r"https?://[^\s]+"),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self._patterns:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True
```

Register it in `logconfig.yaml` and add it to the console handler:

```yaml
filters:
  correlation_id:
    (): asgi_correlation_id.CorrelationIdFilter
    uuid_length: 32
    default_value: "-"
  app_info:
    (): octobot_mcp.config.log_filters.AppInfoFilter
  sensitive_data:
    (): octobot_mcp.config.log_filters.SensitiveDataFilter

handlers:
  console:
    filters: [correlation_id, app_info, sensitive_data]
```

This filter is a final safety net. The primary controls remain suppressing HTTP
client request logs and never attaching sensitive values to application logs.

## 10. Tool Descriptions

### 10.1 `get_service_dictionary`

Replace the claim that every `columns[].name` is valid for both operations with:

```text
Use columns where is_output_column=true, or names listed in
selectable_columns, for select. A required filter may be filter-only and must
not be projected. Use column names verbatim.
```

### 10.2 `apply_filters`

Add these rules to the workflow description:

```text
Use only selectable_columns for select.
Use default_output_columns only when the user did not request output fields.
Use allowed dictionary columns for filters.
Required filter columns are not automatically output columns.
```

The backend validator remains authoritative; docstrings only improve tool
selection by the model.

## 11. Regression Tests

Add focused tests for these contracts.

### 11.1 Registry

```python
def test_default_outputs_are_selectable() -> None:
    for service in list_service_schemas():
        schema = get_service_schema(service["service_name"])
        assert set(schema.default_output_columns) <= set(
            schema.selectable_columns
        )


def test_aliases_target_real_columns() -> None:
    for service in list_service_schemas():
        schema = get_service_schema(service["service_name"])
        allowed = {name.lower() for name in schema.allowed_columns}
        assert all(
            target.lower() in allowed
            for target in schema.aliases.values()
        )
```

### 11.2 Discovery consistency

```python
def test_every_discovered_service_has_a_schema(
    filtered_discovery_payload,
) -> None:
    for entry in discovery_entries(filtered_discovery_payload):
        assert supports_service_schema(discovery_name(entry))
```

Use the real response field names in the fixture.

### 11.3 Select versus filter validation

```python
async def test_filter_only_column_is_rejected_in_select(
    service,
    valid_request,
    mocker,
) -> None:
    provider_get = mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(),
    )
    valid_request.select = ["filter_only_field"]

    result = await service.apply_filters(valid_request)

    provider_get.assert_not_awaited()
    assert result["error"]["code"] == "INVALID_SELECT_COLUMNS"


async def test_filter_only_column_remains_valid_filter(
    service,
    valid_request,
) -> None:
    valid_request.select = ["known_output_field"]
    valid_request.filters = ["filter_only_field=synthetic-value"]

    service._validate_request_schema(valid_request)
```

### 11.4 Provider error normalization

```python
async def test_provider_400_returns_structured_error(
    service,
    valid_request,
    mocker,
) -> None:
    mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(
            side_effect=InvalidParamsError(
                "Upstream rejected the request",
                {
                    "error_code": "UPSTREAM_REQUEST_REJECTED",
                    "provider_status": 400,
                    "retryable": False,
                },
            )
        ),
    )

    result = await service.apply_filters(valid_request)

    assert result["status"] == "ERROR"
    assert result["records"] == []
    assert result["error"]["code"] == (
        "UPSTREAM_REQUEST_REJECTED"
    )
    assert result["error"]["retryable"] is False
```

Also test timeout, rate limit, authorization, not found, and 5xx mappings.

### 11.5 No chained HTTP exception

```python
async def test_mapped_http_error_suppresses_original_cause() -> None:
    with pytest.raises(CitiMCPToolError) as caught:
        await decorated_failing_call()

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
```

### 11.6 Log safety

```python
def test_provider_error_logs_contain_no_request_data(caplog) -> None:
    combined = "\n".join(
        record.getMessage() for record in caplog.records
    ).lower()

    assert "http://" not in combined
    assert "https://" not in combined
    assert "$select=" not in combined
    assert "authorization" not in combined
    assert "synthetic-account-value" not in combined
```

Use only synthetic identifiers in committed tests.

## 12. Implementation Order

1. Add the registry and error-path regression tests.
2. Add `is_output_column` as the final `ColumnSchema` field.
3. Add `selectable_columns` and `ServiceSchema.__post_init__()` checks.
4. Verify and correct the provider-rejected column metadata.
5. Filter discovery to registered service names.
6. Add selectable metadata to `get_service_dictionary()`.
7. Split select validation from filter validation.
8. Replace `exc.data` access with `exc.details`.
9. Enlarge the `apply_filters()` exception boundary.
10. Add safe HTTP error codes and `from None`.
11. Suppress `httpx` and `httpcore` INFO logs.
12. Register the redaction filter.
13. Update both MCP tool descriptions.
14. Run unit tests and a nonproduction end-to-end request.

## 13. Acceptance Criteria

```text
[ ] Discovery never advertises a service without a registered schema.
[ ] Unknown dictionary requests return a structured error, not a traceback.
[ ] A filter-only field is rejected locally when included in select.
[ ] The same field remains valid in filters.
[ ] Invalid select requests never call the provider.
[ ] Every default output column is selectable at process startup.
[ ] A request for one output field sends a narrow projection.
[ ] Expected provider 4xx/5xx/timeout failures return structured tool results.
[ ] Error details survive because the service reads exc.details.
[ ] Expected HTTP failures have no explicit chained cause.
[ ] Logs contain no complete provider URL, query, credentials, or identifiers.
[ ] Existing successful and no-data behavior remains unchanged.
```

## 14. Remaining Inputs for a Compile-Ready Patch

The screenshots are sufficient for the design and all locations above. Two
small artifacts are still required before writing an exact patch against the
real repository:

1. A sanitized `get_filter_values()` JSON response, preserving only its key
   names and value types. This determines the discovery item/name/count fields.
2. The text of `octobot_mcp/config/log_filters.py`. This ensures the new filter
   is merged without duplicating imports or conflicting with `AppInfoFilter`.

The existing backend test files are also useful so the regression tests follow
the repository's fixtures and async test style, but they are not needed to
locate the production fixes.
