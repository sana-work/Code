# Octobot Selectable Columns, Provider Error, and Log Redaction Fix

## 1. Purpose

This document defines the exact stabilization changes required for the current
generic `apply_filters` implementation. It addresses three confirmed defects:

1. The schema registry does not distinguish columns that may appear in
   `$select` from columns that may be used only as filters.
2. Provider failures raised after local validation escape the structured tool
   result handler and become generic MCP execution errors.
3. Provider URLs and business identifiers are visible in ordinary logs.

The supplied provider response was:

```text
400 Column projection not found:
OPTION, SFACNTNM, EARLY_RESPONSE_DEADLINE_DATE
```

The request asked for Pay Date but sent a large default projection. The request
also exposed its complete provider URL and filter values in the logs.

## 2. Line-Number Convention

The line numbers below come from the supplied source screenshots and production
trace. Existing edits may shift them. The function or class name is the
authoritative location.

Before editing, locate the current symbols:

```bash
rg -n "class ColumnSchema|class ServiceSchema|_SCHEMA_BY_NAME|def get_service_dictionary|def _validate_request_schema|def apply_filters|def _authorized_get|raise_for_status|HTTPStatusError" octobot_mcp
```

Do not create duplicate classes or duplicate registries when a line number has
moved.

## 3. Change Summary

| Order | File | Screenshot/trace line | Function or symbol | Required change |
|---|---|---:|---|---|
| 1 | `octobot_mcp/config/apigee_schema_registry.py` | Class is above screenshot line 294 | `ColumnSchema` | Add `is_output_column` |
| 2 | Same file | Class is above screenshot line 294 | `ServiceSchema` | Add `selectable_columns` and startup invariants |
| 3 | Same file | Service declarations above line 294 | Affected events schema | Correct the three rejected column definitions |
| 4 | `octobot_mcp/services/apigee_service.py` | 187-211 | `get_service_dictionary()` | Return output-column metadata |
| 5 | Same file | 213 onward; latest screenshot around 225-269 | `_validate_request_schema()` | Validate `$select` against selectable columns |
| 6 | Same file | Production trace line 310 | `apply_filters()` | Normalize provider exceptions into a tool result |
| 7 | Same file | Production trace line 114 | `_authorized_get()` | Keep raw HTTP details inside the provider boundary |
| 8 | `octobot_mcp/utils/exceptions.py` | Production trace lines 116-120 | HTTP exception wrapper | Preserve safe status data and suppress exception chaining |
| 9 | `octobot_mcp/logconfig.yaml` | Logger configuration | `httpx`/`httpcore` loggers | Disable full request URL logging |
| 10 | `octobot_mcp/config/log_filters.py` | Existing log filter | Redaction filter | Redact sensitive fields as defense in depth |
| 11 | `octobot_mcp/tools/apigee_tools.py` | 69-134 | `apply_filters()` tool description | Explain selectable versus filter-only fields |
| 12 | `tests/` | New tests | Focused regression tests | Lock all corrected behavior |

## 4. Registry Changes

### 4.1 File

```text
octobot_mcp/config/apigee_schema_registry.py
```

### 4.2 Location

Find:

```python
class ColumnSchema
```

This class is above `_SCHEMA_BY_NAME`, which appears around screenshot lines
294-297.

### 4.3 Change `ColumnSchema`

Add one explicit output capability flag:

```python
@dataclass(frozen=True)
class ColumnSchema:
    name: str
    english_name: str
    description: str
    data_type: str
    is_required_filter: bool = False
    is_default_output: bool = False
    is_output_column: bool = True
```

If `ColumnSchema` is a Pydantic model rather than a dataclass, add the same
field using the existing Pydantic style:

```python
is_output_column: bool = True
```

The default preserves existing definitions during migration. Every known
filter-only column must then be marked `False` explicitly.

### 4.4 Change `ServiceSchema`

Find:

```python
class ServiceSchema
```

Add a selectable-column set that is distinct from the existing
`allowed_columns` set:

```python
@property
def selectable_columns(self) -> frozenset[str]:
    return frozenset(
        column.name
        for column in self.columns
        if column.is_output_column
    )
```

Keep `allowed_columns` temporarily for filter validation and backward
compatibility. Do not use it to validate `$select` after this change.

Add a startup invariant:

```python
def validate_contract(self) -> None:
    selectable_lower = {
        column.lower() for column in self.selectable_columns
    }
    invalid_defaults = sorted(
        column
        for column in self.default_output_columns
        if column.lower() not in selectable_lower
    )
    if invalid_defaults:
        raise ValueError(
            "default_output_columns must be selectable: "
            f"{invalid_defaults}"
        )
```

Call this during registry construction or application startup for every
registered service:

```python
for schema in _SCHEMA_BY_NAME.values():
    schema.validate_contract()
```

If `default_output_columns` is derived from `ColumnSchema`, reject invalid
metadata directly:

```python
invalid_defaults = [
    column.name
    for column in self.columns
    if column.is_default_output and not column.is_output_column
]
```

### 4.5 Correct the affected service metadata

Locate the service whose portable ID appears in the failed provider URL. Do not
put the portable ID into logs or user-facing output.

For `sfacntnm`, keep it available as a required filter but not as an output
projection:

```python
ColumnSchema(
    name="sfacntnm",
    english_name="Safe Account Number",
    description="Safe account number used to restrict the request.",
    data_type="string",
    is_required_filter=True,
    is_default_output=False,
    is_output_column=False,
)
```

For `option` and `early_response_deadline_date`, first compare the current
registry names with the provider's current service dictionary.

If the provider has different source names, replace the registry names with the
exact provider names. If the columns are filter-only or unavailable, use:

```python
is_default_output=False,
is_output_column=False,
```

Do not remove a required filter merely because it is not selectable.

### 4.6 Registry acceptance conditions

For every service:

```text
default_output_columns is a subset of selectable_columns
required_filter_columns may contain non-selectable columns
all registry source names exactly match the provider contract
```

## 5. Dictionary Response Changes

### 5.1 File and location

```text
octobot_mcp/services/apigee_service.py
get_service_dictionary(), screenshot lines 187-211
```

The current function returns each column's `name`, `english_name`,
`description`, `data_type`, `is_required_filter`, and `is_default_output`.

### 5.2 Add column capability

Inside the per-column dictionary, add:

```python
"is_output_column": column.is_output_column,
```

At the top level of the returned dictionary, add:

```python
"selectable_columns": sorted(schema.selectable_columns),
```

The resulting shape should include:

```python
return {
    "required_filter_columns": sorted(
        schema.required_filter_columns
    ),
    "default_output_columns": list(
        schema.default_output_columns
    ),
    "selectable_columns": sorted(schema.selectable_columns),
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

The portable ID may remain in the internal tool response if required by the
current generic tool contract, but the agent and formatter must not expose it
to the user.

## 6. Local `$select` Validation

### 6.1 File and location

```text
octobot_mcp/services/apigee_service.py
_validate_request_schema(), screenshot line 213 onward
```

In the supplied screenshots, the old code creates `allowed_lower` from
`schema.allowed_columns` around lines 227-228 and uses it for `invalid_select`.
That is the defect.

### 6.2 Replace only the select validation

Replace:

```python
allowed_lower = frozenset(
    column.lower() for column in schema.allowed_columns
)

invalid_select = sorted({
    column
    for column in request.select
    if column.strip().lower() not in allowed_lower
})
```

with:

```python
selectable_lower = frozenset(
    column.lower() for column in schema.selectable_columns
)
selectable_columns = sorted(schema.selectable_columns)

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
            "service_name": request.service_name,
            "invalid_select_columns": invalid_select,
            "selectable_columns": selectable_columns,
        },
    )
```

### 6.3 Keep filter validation separate

The filter-field validation must not use `selectable_lower`. Continue using the
broader allowed/filterable set:

```python
filterable_lower = frozenset(
    column.lower() for column in schema.allowed_columns
)

invalid_filter_fields = sorted(
    field
    for field in filter_fields
    if field.lower() not in filterable_lower
)
```

This allows `sfacntnm` to be used as a filter while preventing it from being
sent in `$select`.

### 6.4 Recommended next refinement

After the stabilization patch, add `is_filterable` and derive a true
`filterable_columns` set. Until the source metadata for optional filters is
confirmed, do not incorrectly assume that only required filters are
filterable.

## 7. Provider Error Normalization

### 7.1 Confirmed escape point

```text
octobot_mcp/services/apigee_service.py
apply_filters(), production trace line 310
```

The existing structured handler catches errors from
`_validate_request_schema()` around screenshot lines 282-304. The provider call
occurs after that handler, so its exception escapes to FastMCP.

### 7.2 Add a shared result helper

Inside `ApigeeService`, add:

```python
@staticmethod
def _error_result(
    *,
    code: str,
    message: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ERROR",
        "records": [],
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        },
    }
```

Use the same helper for local validation results where practical. Keep
`NEEDS_CLARIFICATION` for `MISSING_REQUIRED_FILTER`.

### 7.3 Wrap the provider call

Immediately around the current line 310 call, add:

```python
try:
    response = await self._authorized_get(url)
except InvalidParamsError as exc:
    source_details = getattr(exc, "data", None)
    if not isinstance(source_details, dict):
        source_details = {}

    safe_details = {
        key: source_details[key]
        for key in (
            "provider_status",
            "correlation_id",
        )
        if source_details.get(key) is not None
    }

    return self._error_result(
        code=source_details.get(
            "error_code",
            "UPSTREAM_REQUEST_REJECTED",
        ),
        message="The provider rejected the request.",
        retryable=False,
        details=safe_details,
    )
except ServiceUnavailableError as exc:
    source_details = getattr(exc, "data", None)
    if not isinstance(source_details, dict):
        source_details = {}

    return self._error_result(
        code=source_details.get(
            "error_code",
            "UPSTREAM_UNAVAILABLE",
        ),
        message="The provider is temporarily unavailable.",
        retryable=bool(source_details.get("retryable", False)),
        details={
            key: source_details[key]
            for key in (
                "provider_status",
                "correlation_id",
            )
            if source_details.get(key) is not None
        },
    )
```

Import the actual service-unavailable exception class already used by
`octobot_mcp/utils/exceptions.py`. If its name differs, use the repository's
existing class rather than introducing an alias solely for this snippet.

Do not catch `Exception` here. Unexpected programming defects should remain
observable to operations instead of being mislabeled as provider failures.

### 7.4 Prefer structured HTTP parameters

The failed trace contains a manually assembled query URL. Change the provider
call from a complete query string to a path and `params` object:

```python
path = (
    f"/api/services/{request.service_portable_id}/filter"
)
params = self._build_filter_params(request)
response = await self._authorized_get(path, params=params)
```

Update `_authorized_get()` to accept:

```python
async def _authorized_get(
    self,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
```

Pass `params=params` to the HTTP client. Do not log `params`.

## 8. HTTP Exception Mapping

### 8.1 File and location

```text
octobot_mcp/utils/exceptions.py
HTTP wrapper around production trace lines 113-123
```

The trace shows `httpx.HTTPStatusError` being converted to
`InvalidParamsError: Upstream rejected the request`. The original exception is
currently chained, which exposes the full URL in the traceback.

### 8.2 Preserve safe fields only

Use a status classifier:

```python
def _provider_error_metadata(
    response: httpx.Response,
) -> tuple[str, bool]:
    status = response.status_code

    if status == 400:
        return "UPSTREAM_INVALID_REQUEST", False
    if status in {401, 403}:
        return "UPSTREAM_AUTHORIZATION_FAILED", False
    if status == 429:
        return "UPSTREAM_RATE_LIMITED", True
    if status in {502, 503, 504}:
        return "UPSTREAM_UNAVAILABLE", True
    if status >= 500:
        return "UPSTREAM_FAILURE", False
    return "UPSTREAM_REQUEST_REJECTED", False
```

In the `except httpx.HTTPStatusError` branch:

```python
except httpx.HTTPStatusError as exc:
    response = exc.response
    error_code, retryable = _provider_error_metadata(response)

    data = {
        "error_code": error_code,
        "provider_status": response.status_code,
        "retryable": retryable,
        "correlation_id": response.headers.get(
            "x-correlation-id"
        ),
    }

    if response.status_code == 400:
        raise InvalidParamsError(
            "Upstream rejected the request",
            data,
        ) from None

    raise ServiceUnavailableError(
        "Upstream service failure",
        data,
    ) from None
```

`from None` is required. It prevents the original `HTTPStatusError`, complete
URL, query parameters, and identifiers from appearing in the normal traceback.

Do not copy the provider response body into `data`.

## 9. Log Redaction

### 9.1 Disable `httpx` request logging

File:

```text
octobot_mcp/logconfig.yaml
```

Add or update:

```yaml
loggers:
  httpx:
    level: WARNING
    propagate: false
  httpcore:
    level: WARNING
    propagate: false
```

If the file already defines `loggers`, merge these entries. Do not create a
second top-level `loggers` key.

### 9.2 Safe application logging

File and location:

```text
octobot_mcp/services/apigee_service.py
_authorized_get(), production trace line 114
```

Never log the complete URL, request params, filter values, authorization
headers, cookies, certificates, or response body.

Use:

```python
logger.warning(
    "Provider request failed",
    extra={
        "provider_status": response.status_code,
        "correlation_id": response.headers.get(
            "x-correlation-id"
        ),
    },
)
```

Service name may be logged if it is approved operational metadata. Portable
IDs and account/event identifiers should not be logged.

### 9.3 Defense-in-depth redaction

File:

```text
octobot_mcp/config/log_filters.py
```

Add redaction for structured log attributes if those attributes can be present:

```python
SENSITIVE_LOG_FIELDS = {
    "authorization",
    "cookie",
    "token",
    "client_secret",
    "service_portable_id",
    "corp",
    "sfacntnm",
    "account_id",
    "event_id",
    "url",
    "params",
}


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for field in SENSITIVE_LOG_FIELDS:
            if hasattr(record, field):
                setattr(record, field, "[REDACTED]")
        return True
```

Register the filter using the repository's existing logging configuration
pattern. This is a backup control; preventing sensitive values from reaching
the logger is the primary control.

## 10. MCP Tool Description

### 10.1 File and location

```text
octobot_mcp/tools/apigee_tools.py
apply_filters(), screenshot lines 69-134
```

Add these rules to the tool description:

```text
Use only dictionary columns where is_output_column=true in select.
Required filter columns are not automatically output columns.
When the user asks for specific fields, select only those fields.
Use default_output_columns only when no output field was requested.
```

The server-side validator remains authoritative. The tool description is not a
replacement for code validation.

## 11. Tests

### 11.1 Registry tests

Suggested file:

```text
tests/test_apigee_schema_registry.py
```

```python
def test_default_outputs_are_selectable() -> None:
    for schema in _SCHEMA_BY_NAME.values():
        assert set(schema.default_output_columns) <= set(
            schema.selectable_columns
        )
```

```python
def test_required_filter_can_be_non_selectable() -> None:
    schema = get_service_schema("view_events_entitlements")

    assert "sfacntnm" in schema.required_filter_columns
    assert "sfacntnm" not in schema.selectable_columns
```

Use the registry's actual canonical service name.

### 11.2 Validation tests

Suggested file:

```text
tests/test_apigee_service.py
```

```python
async def test_filter_only_column_is_rejected_in_select(
    service,
    mocker,
) -> None:
    authorized_get = mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(),
    )

    request = make_valid_events_request(
        select=["sfacntnm"],
        filters=[
            "corp=2436705637002",
            "sfacntnm=17709700000H2",
        ],
    )

    result = await service.apply_filters(request)

    authorized_get.assert_not_awaited()
    assert result["error"]["code"] == (
        "INVALID_SELECT_COLUMNS"
    )
```

```python
async def test_filter_only_column_is_allowed_as_filter(
    service,
    mocker,
) -> None:
    response = mock_provider_response(
        status_code=200,
        json_data={"records": [{"pay_date": "2026-09-01"}]},
    )
    authorized_get = mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(return_value=response),
    )

    request = make_valid_events_request(
        select=["pay_date"],
        filters=[
            "corp=2436705637002",
            "sfacntnm=17709700000H2",
        ],
    )

    result = await service.apply_filters(request)

    authorized_get.assert_awaited_once()
    assert result.get("error") is None
```

Use synthetic values in committed tests rather than real identifiers.

### 11.3 Provider error tests

```python
async def test_provider_400_returns_structured_error(
    service,
    mocker,
) -> None:
    mocker.patch.object(
        service,
        "_authorized_get",
        new=mocker.AsyncMock(
            side_effect=InvalidParamsError(
                "Upstream rejected the request",
                {
                    "error_code": "UPSTREAM_INVALID_REQUEST",
                    "provider_status": 400,
                },
            )
        ),
    )

    result = await service.apply_filters(
        make_valid_events_request(select=["pay_date"])
    )

    assert result["status"] == "ERROR"
    assert result["records"] == []
    assert result["error"]["code"] == (
        "UPSTREAM_INVALID_REQUEST"
    )
    assert result["error"]["retryable"] is False
```

### 11.4 Log safety test

```python
def test_provider_error_does_not_log_sensitive_url(
    caplog,
) -> None:
    combined = "\n".join(
        record.getMessage() for record in caplog.records
    )

    assert "sfacntnm=" not in combined
    assert "corp=" not in combined
    assert "/api/services/" not in combined
    assert "Authorization" not in combined
```

Also test `401`, `403`, `429`, `500`, `502`, `503`, `504`, connect timeout,
and read timeout.

## 12. Implementation Order

Apply and deploy the changes in this order:

1. Add failing tests for invalid output projection, provider `400`, and log
   leakage.
2. Add `is_output_column` and `selectable_columns`.
3. Correct the affected service metadata.
4. Add the registry startup invariant.
5. Return output capabilities from `get_service_dictionary()`.
6. Validate `select` against `selectable_columns`.
7. Normalize expected provider errors in `apply_filters()`.
8. Preserve safe provider status metadata in the HTTP exception mapper.
9. Suppress exception chaining with `from None`.
10. Disable `httpx` and `httpcore` request logging.
11. Add defense-in-depth structured-log redaction.
12. Update the MCP tool description.
13. Run the complete test suite.
14. Deploy to a nonproduction environment.
15. Verify the Pay Date request produces a narrow projection.

## 13. Expected Request After the Fix

For a user asking only for Pay Date, the provider request should conceptually
contain:

```text
$select=pay_date
corp=<event identifier>
sfacntnm=<safe account identifier>
```

It must not project `sfacntnm` merely because `sfacntnm` is a required filter.
It must not send every default column when the user requested one field.

## 14. Acceptance Criteria

The fix is complete only when all conditions below pass:

```text
[ ] A filter-only field is rejected locally when included in select.
[ ] The same field remains valid in filters.
[ ] Invalid select requests never call the provider.
[ ] Every default output column is selectable at startup.
[ ] Pay Date-only requests do not send the full default projection.
[ ] Provider 400 returns a structured ERROR tool result.
[ ] FastMCP does not emit a generic tool-execution error for expected 4xx cases.
[ ] Ordinary logs contain no complete provider URL.
[ ] Ordinary logs contain no account, event, token, or cookie values.
[ ] The agent receives a safe error code and never receives a stack trace.
[ ] Existing successful and no-data behavior remains unchanged.
```

