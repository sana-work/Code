# Octobot MCP API and Function Flow

Date: 2026-09-01

Status: target implementation flow

## 1. End-to-end summary

```text
MCP startup
  -> load PostgreSQL metadata
  -> validate all five services
  -> build immutable in-memory registry
  -> expose five MCP tools
  -> server becomes ready

Each request
  Specialist Sub-Agent
  -> service-specific MCP tool
  -> shared service executor
  -> in-memory metadata lookup
  -> request validation and field resolution
  -> provider request builder
  -> provider REST API
  -> response normalizer
  -> structured tool result
  -> Specialist Sub-Agent
  -> Formatter Agent
  -> final JSON validator
  -> User
```

## 2. MCP startup flow

This happens once for every MCP server process:

```text
start_mcp_server()
  -> initialize_metadata_registry()
      -> ServiceRepository.load_all_services_with_columns()
      -> MetadataRegistry.build()
      -> validate_expected_tool_bindings()
      -> calculate_snapshot_fingerprint()
      -> freeze()
  -> register five MCP tools
  -> readiness = READY
```

Suggested implementation:

```python
async def initialize_mcp_runtime() -> ServiceRuntime:
    rows = await service_repository.load_all_services_with_columns()

    registry = MetadataRegistry.build(rows)

    registry.validate_expected_tools({
        "query_as_events_entitlements": "ASSET_SERVICES",
        "query_as_cash_entitlements": "ASSET_SERVICES",
        "query_tm_eod_security_transactions": "TRANSACTION_MANAGEMENT",
        "query_tm_current_securities_transactions": "TRANSACTION_MANAGEMENT",
        "query_tm_current_securities_transactions_with_settlement_instruction_details":
            "TRANSACTION_MANAGEMENT",
    })

    return ServiceRuntime(
        registry=registry.freeze(),
        provider_client=ProviderClient.from_environment(),
    )
```

The MCP server must fail readiness if any service, portable ID, dictionary, default output, alias, or domain binding is invalid.

After startup completes, normal requests make zero PostgreSQL calls.

## 3. Agent-to-MCP call

The Specialist Sub-Agent calls a registered MCP tool using business data only:

```json
{
  "requestId": "req-123",
  "entities": {
    "safeAccount": "4205640693"
  },
  "filters": [
    {
      "field": "transactionStatus",
      "operator": "EQUALS",
      "value": "FAILED"
    }
  ],
  "requestedFields": [
    "transactionId",
    "transactionStatus",
    "settlementDate"
  ],
  "pagination": {
    "limit": 100,
    "offset": 0
  }
}
```

The agent does not send:

```text
portable_id
service_name
provider column names
provider URL
raw filter expression
authentication information
```

## 4. Service-specific MCP tool wrapper

Each of the five MCP tools is a thin wrapper:

```python
TOOL_NAME = "query_tm_current_securities_transactions"


@mcp.tool(name=TOOL_NAME)
async def query_tm_current_securities_transactions(
    request: ServiceQueryRequest,
) -> ServiceQueryResult:
    return await service_runtime.execute(
        tool_name=TOOL_NAME,
        expected_domain="TRANSACTION_MANAGEMENT",
        request=request,
    )
```

The wrapper contains:

- registered tool name
- expected business domain
- business-facing description
- input and output schemas

It does not contain the portable ID or provider request logic.

## 5. Shared execution flow

Every service-specific wrapper enters the same shared function:

```text
ServiceRuntime.execute()
  -> registry.require(tool_name)
  -> service.assert_domain(expected_domain)
  -> request_validator.validate()
  -> field_resolver.resolve()
  -> filter_validator.validate()
  -> provider_request_builder.build()
  -> provider_client.execute_filter()
  -> response_normalizer.normalize()
  -> ServiceQueryResult
```

Suggested implementation:

```python
async def execute(
    self,
    tool_name: str,
    expected_domain: str,
    request: ServiceQueryRequest,
) -> ServiceQueryResult:
    service = self.registry.require(tool_name)
    service.assert_domain(expected_domain)

    resolved_request = resolve_and_validate_request(
        request=request,
        service=service,
    )

    provider_request = build_provider_request(
        service=service,
        request=resolved_request,
    )

    try:
        provider_response = await self.provider_client.filter_service(
            portable_id=service.portable_id,
            request_id=request.request_id,
            payload=provider_request,
        )
    except ProviderError as error:
        return normalize_provider_error(
            tool_name=tool_name,
            request_id=request.request_id,
            error=error,
        )

    return normalize_provider_response(
        tool_name=tool_name,
        service=service,
        response=provider_response,
    )
```

## 6. Detailed request processing sequence

For every tool call, the shared executor performs these steps in order:

1. Validate `requestId`, entities, filters, requested fields, and pagination.
2. Resolve the service definition from the immutable registry using `tool_name`.
3. Verify that the service domain matches the wrapper's `expected_domain`.
4. Resolve business entity and filter names to exactly one approved metadata column.
5. Reject unknown or ambiguous names before calling the provider.
6. Validate operators against the resolved column data types.
7. Validate required-filter rules.
8. Convert values to the provider-required types.
9. Resolve requested output fields or select default output columns.
10. Build the provider request from structured values.
11. Read the service portable ID from the in-memory service definition.
12. Call the provider through the shared provider client.
13. Apply timeout and bounded retry rules.
14. Normalize the provider response or error.
15. Return the common `ServiceQueryResult` contract.

## 7. Provider REST API call

The shared provider client makes the request:

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
    "TRANS_ID",
    "TRANS_STATUS",
    "SETTLEMENT_DATE"
  ],
  "filters": [
    {
      "column": "SAFE_ACCOUNT",
      "operator": "EQ",
      "value": "4205640693"
    },
    {
      "column": "TRANS_STATUS",
      "operator": "EQ",
      "value": "FAILED"
    }
  ],
  "limit": 100,
  "offset": 0
}
```

The exact provider payload field names must follow the existing provider API contract. The important boundary is that deterministic MCP code produces this payload; the agent does not construct it.

Provider base URL, authentication URLs, credentials, certificates, timeouts, and retry settings come from deployment configuration. They are not stored in service metadata or supplied by the agent.

## 8. Response normalization

The provider response is converted into the common tool contract:

```json
{
  "requestId": "req-123",
  "toolName": "query_tm_current_securities_transactions",
  "domain": "TRANSACTION_MANAGEMENT",
  "status": "SUCCESS",
  "tables": [
    {
      "name": "Current Securities Transactions",
      "columns": [
        "transactionId",
        "transactionStatus",
        "settlementDate"
      ],
      "rows": [
        {
          "transactionId": "TX-1001",
          "transactionStatus": "FAILED",
          "settlementDate": "2026-08-31"
        }
      ]
    }
  ],
  "errors": []
}
```

Provider column names are translated back to business field names before the result leaves the MCP server.

Possible tool statuses are:

```text
SUCCESS
NO_DATA
ERROR
```

The error response contains a safe error code, tool name, retryability, and correlation ID. Provider response bodies, tokens, internal URLs, certificates, and stack traces remain only in protected logs.

## 9. Multiple-service query flow

Example user request:

```text
Show current failed transactions and their settlement-instruction details.
```

The TM Specialist Sub-Agent selects:

```text
query_tm_current_securities_transactions
query_tm_current_securities_transactions_with_settlement_instruction_details
```

### 9.1 Independent service calls

If both services can be called using only user-supplied business entities, the agent runtime executes them in parallel:

```python
current_result, settlement_result = await asyncio.gather(
    call_current_transactions_tool(request),
    call_settlement_instructions_tool(request),
)
```

### 9.2 Dependent service calls

If the settlement-instruction service requires transaction IDs returned by the current-transactions service, execution is sequential:

```text
Current Transactions tool
  -> obtain documented transaction IDs
  -> Settlement Instructions tool using those transaction IDs
```

Only documented business keys may be passed between calls. Each tool call independently enters the shared MCP executor and creates its own provider API request.

Cross-service orchestration belongs to the Specialist Sub-Agent runtime. It does not belong inside the shared MCP executor.

## 10. Specialist response flow

The Specialist Sub-Agent keeps every normalized service result and returns:

```json
{
  "requestId": "req-123",
  "domain": "TRANSACTION_MANAGEMENT",
  "intent": "Retrieve failed current transactions and settlement instructions",
  "status": "SUCCESS",
  "serviceResults": [],
  "missingInputs": []
}
```

If one service succeeds and another fails:

```text
successful table is preserved
failed service becomes a structured error
specialist status = PARTIAL
final status = PARTIAL
```

The specialist does not build the final user-facing JSON.

## 11. Final response flow

```text
ServiceQueryResult[]
  -> Specialist Sub-Agent creates SpecialistResponse
  -> Formatter Agent receives AS/TM SpecialistResponse objects
  -> Formatter builds final tables, attributes, toolsUsed, and status
  -> Final JSON Validator validates the production schema
  -> validated response returns to the User
```

The Formatter Agent is outside the MCP server and has no MCP tools or provider access.

## 12. Proposed MCP module structure

```text
octobot-mcp/
  server.py
  startup.py
  contracts/
    service_query_request.py
    service_query_result.py
    tool_error.py
  tools/
    as_events_entitlements.py
    as_cash_entitlements.py
    tm_eod_security_transactions.py
    tm_current_securities_transactions.py
    tm_current_securities_transactions_with_settlement_instruction_details.py
  runtime/
    service_runtime.py
    request_validator.py
    field_resolver.py
    filter_validator.py
    provider_request_builder.py
    response_normalizer.py
    error_normalizer.py
  metadata/
    service_repository.py
    metadata_registry.py
  providers/
    provider_client.py
    authentication.py
  tests/
```

## 13. Responsibility summary

| Layer | Responsibility |
| --- | --- |
| Specialist Sub-Agent | Select the smallest sufficient domain tools and coordinate multiple calls |
| Service-specific tool wrapper | Expose a stable business contract and pass its own `tool_name` and domain to shared code |
| Immutable metadata registry | Provide constant-time service and dictionary lookup with no request-time SQL |
| Shared service executor | Validate, resolve fields, build provider requests, invoke the provider, and normalize results |
| Provider client | Own HTTP transport, authentication, TLS, timeout, and retry behavior |
| Specialist response | Preserve normalized service results and partial failures |
| Formatter Agent | Perform all final table, attribute, and status formatting |
| Final JSON validator | Enforce the unchanged production response schema |
