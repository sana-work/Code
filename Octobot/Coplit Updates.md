Apply a narrow correction to the current working tree. Do not redo or revert the completed AS cleanup.

The mappings in `asset_services_output_fields.py` are already reviewed and approved. They are the authoritative, checked-in source of truth. No additional field-contract document, provisional status, business-owner review, or approval workflow is required.

Remove the unnecessary review layer:

1. Keep these required implementation elements unchanged:
   - `asset_services_output_fields.py`
   - `EVENTS_ENTITLEMENTS_OUTPUT_FIELDS`
   - `CASH_ENTITLEMENTS_OUTPUT_FIELDS`
   - `ServiceToolContract` and `FieldContract`
   - startup validation of mapped provider columns
   - exact output-enum and provider-leakage tests
   - Events `safe_account` filter-only behavior
   - Cash `safe_account` selectable-output behavior
   - the four approved Safe Account aliases
   - the 100-record agent limit
   - comma-filter rejection
   - the two-tool inventory
   - all completed SampleDomain, HealthTools, dev-client, lint, and test cleanup

2. Remove metadata added only for the unnecessary review workflow:
   - `PROVISIONAL_PENDING_BUSINESS_REVIEW`
   - `REVIEW_STATUS`
   - `MAPPING_SOURCE`
   - similar production-approval flags or constants

3. Delete these duplicate artifacts:
   - `AS_Field_Contract.md`
   - `generate_as_field_contract_doc.py`
   - `test_as_field_contract_doc.py`
   - exports or configuration used only by those artifacts

4. Remove all documentation and report statements claiming:
   - mappings are provisional,
   - mappings require additional human review,
   - field wording is awaiting business-owner approval,
   - mapping approval is a production-release blocker.

5. Update references that currently direct readers to `AS_Field_Contract.md`.
   Refer directly to the reviewed mappings in `asset_services_output_fields.py` or the generated MCP tool schema. Do not create another document duplicating the mappings.

6. Keep a concise code comment or docstring explaining only the real schema distinction:
   - Events accepts `safe_account` as a required filter but cannot return it because the provider column is filter-only.
   - Cash can return `safe_account` because its corresponding provider column is selectable.

7. Verify that no unnecessary review artifacts remain:

   `rg -n "PROVISIONAL_PENDING_BUSINESS_REVIEW|AS_Field_Contract|REVIEW_STATUS|MAPPING_SOURCE|required human review|business owner approval" .`

8. Run:
   - `python -m pytest tests/ -q -p no:cacheprovider`
   - `python test_runner.py`
   - `ruff check octobot_mcp tests scripts`
   - the exact two-tool inventory test

The test count may decrease when the obsolete generated-document test is deleted. Explain that expected change; do not recreate a replacement test merely to preserve the count.

The final report must state that the reviewed code mappings are authoritative and that no additional mapping review is required. The only remaining external validation is the Root Agent → AS Specialist → Formatter end-to-end run.