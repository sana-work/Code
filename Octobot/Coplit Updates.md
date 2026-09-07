Perform one final, narrowly scoped cleanup of the current working tree. Preserve all completed behavior and avoid introducing new abstractions.

## Objective

Keep a clean AS-first implementation with generic shared code reusable for Transaction Management later. Only the two Asset Services tools are implemented now.

The output mappings currently in code are already reviewed and approved. No additional field-contract document or human-review workflow is required.

## Required changes

1. Consolidate the approved output mappings:
   - Move `EVENTS_ENTITLEMENTS_OUTPUT_FIELDS` and `CASH_ENTITLEMENTS_OUTPUT_FIELDS` unchanged from `asset_services_output_fields.py` into `contracts/asset_services.py`.
   - Keep the mappings next to their corresponding AS tool contracts.
   - Do not rename, regenerate, reinterpret, or derive any mapping from `english_name`.
   - Build `EventsOutputField` and `CashOutputField` from the approved mapping keys.
   - Ensure each `ServiceToolContract` directly owns its output mapping.
   - Preserve startup validation that every mapped provider column is selectable.
   - Preserve provider-column-to-business-key response normalization.
   - Delete `asset_services_output_fields.py` after updating all imports.

2. Remove the unnecessary mapping-review workflow:
   - Delete `AS_Field_Contract.md`.
   - Delete `generate_as_field_contract_doc.py`.
   - Delete `test_as_field_contract_doc.py`.
   - Remove `PROVISIONAL_PENDING_BUSINESS_REVIEW`, `REVIEW_STATUS`, `MAPPING_SOURCE`, and related metadata.
   - Remove documentation claiming the mappings are provisional or require further approval.
   - Do not create a replacement mapping document or generator.

3. Preserve the correct Safe Account contract:
   - Approved aliases are exactly `safe account`, `safe account number`, `security account`, and `security account id`.
   - Do not include `safekeeping_number`.
   - Preserve identifier strings exactly, including leading zeroes.
   - Events uses `safe_account` as a required filter but cannot return it because its provider column is filter-only.
   - Cash may return `safe_account` because its corresponding provider column is selectable.
   - Never fabricate `safe_account` in Events records.

4. Preserve all completed runtime protections:
   - Exactly two registered MCP tools:
     - `query_as_events_entitlements`
     - `query_as_cash_entitlements`
   - Agent-facing maximum result limit remains 100.
   - The 400000 provider transport ceiling remains internal and is never exposed as the tool limit.
   - Invalid limits and offsets are rejected, never clamped.
   - Only equality filters are supported.
   - Comma-containing single-value filters are rejected until provider list/OR grammar is verified.
   - Filter values cannot alter operators, columns, or query parameters.
   - Provider errors remain normalized and allowlisted.
   - Provider columns, portable IDs, credentials, URLs, and internal details never appear in agent-visible results.

5. Preserve completed repository cleanup:
   - Do not restore SampleDomain, HealthTools, dummy tools, generic discovery tools, or removed Apigee-named internal implementations.
   - Preserve the `/ready` endpoint.
   - Preserve the updated AS `dev_client.py`.
   - Keep external `APIGEE_`, Helm, and Vault names only at the documented deployment compatibility boundary.
   - Do not add Transaction Management tools yet.
   - Do not disable pytest cache globally in `pyproject.toml`.

6. Update imports, `__all__` exports, tests, README, and `Octobot_MCP_API_Function_Flow.md` only where necessary to reflect this consolidation.
   - Remove references to deleted files and review requirements.
   - State that the code mappings in `contracts/asset_services.py` are authoritative.
   - Do not duplicate the full mapping table in documentation.

## Verification

Run and report the exit code for:

- `python -m pytest tests/ -q -p no:cacheprovider`
- `python test_runner.py`
- `ruff check octobot_mcp tests scripts`
- the exact MCP tool-inventory test

Also verify there are no remaining references to:

- `asset_services_output_fields`
- `AS_Field_Contract`
- `generate_as_field_contract_doc`
- `PROVISIONAL_PENDING_BUSINESS_REVIEW`
- `REVIEW_STATUS`
- `MAPPING_SOURCE`
- `safekeeping_number`

The test count may decrease because the obsolete generated-document test is deleted. Explain this expected reduction rather than recreating an unnecessary test.

Return a concise factual report listing moved and deleted files, verification results, exact registered tool names, and any genuine unresolved issue. Do not list mapping review as unresolved. After this cleanup, the only remaining external validation is the Root Agent → AS Specialist → Formatter end-to-end run.