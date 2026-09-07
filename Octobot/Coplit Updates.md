Perform only the remaining output-mapping consolidation. Do not change any behavior, mapping value, validation rule, tool schema, or completed cleanup.

1. Move these approved mappings unchanged from `asset_services_output_fields.py` into `contracts/asset_services.py`:
   - `EVENTS_ENTITLEMENTS_OUTPUT_FIELDS`
   - `CASH_ENTITLEMENTS_OUTPUT_FIELDS`

2. Preserve:
   - mapping immutability,
   - all existing mapping entries,
   - `EventsOutputField` and `CashOutputField`,
   - startup validation against selectable provider columns,
   - default-output validation,
   - provider-to-business response normalization,
   - the factual Events-versus-Cash `safe_account` selectability note.

3. Keep each mapping directly beside its corresponding `ServiceToolContract` definition. The AS contract module must become the single authoritative source for:
   - input field mappings,
   - output field mappings,
   - output type aliases,
   - default output fields,
   - maximum result limits.

4. Update every import, export, runtime reference, and test to use `contracts/asset_services.py`.

5. Delete `asset_services_output_fields.py` after confirming it has no remaining references.

6. Do not:
   - generate mappings from `english_name`,
   - create another mapping module,
   - create a field-contract document,
   - add review-status metadata,
   - change any approved business key or provider column,
   - reintroduce deleted SampleDomain, HealthTools, or legacy tools,
   - modify the external deployment compatibility boundary,
   - add TM tools.

7. Verify that this command returns no matches:

   `rg -n "asset_services_output_fields|AS_Field_Contract|PROVISIONAL_PENDING_BUSINESS_REVIEW|REVIEW_STATUS|MAPPING_SOURCE" .`

8. Run:
   - `python -m pytest tests/ -q -p no:cacheprovider`
   - `python test_runner.py`
   - `ruff check octobot_mcp tests`
   - `tests/test_tools.py::test_exact_tool_inventory`

Return a concise report confirming:
- mappings were moved without modification,
- `asset_services_output_fields.py` was deleted,
- `contracts/asset_services.py` is now the authoritative AS contract,
- all command exit codes,
- exactly two MCP tools remain registered.

Do not report any additional mapping-review requirement. The external Root Agent → AS Specialist → Formatter end-to-end run remains the only outstanding validation.