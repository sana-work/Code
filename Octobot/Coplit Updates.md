Perform the last repository-cleanup pass. Do not redesign the completed AS implementation.

1. Remove `safekeeping_number` from the Safe Account aliases unless an authoritative business source explicitly approves it. Retain only:
   - `safe account`
   - `safe account number`
   - `security account`
   - `security account id`

2. Preserve the verified schema behavior:
   - Events uses `safe_account` only as a required filter because `SfAcntNm` is not selectable.
   - Never fabricate `safe_account` in Events records.
   - Cash may return `safe_account` because its provider schema makes the column selectable.
   - Document this difference in the generated field-contract document and tests.

3. Treat all newly hand-authored output mappings as `PROVISIONAL_PENDING_BUSINESS_REVIEW`.
   - Do not call them approved merely because tests pass.
   - Add source and review-status columns to `AS_Field_Contract.md`.
   - Runtime exposure may remain for internal E2E testing, but documentation must state that production release requires business-owner approval.
   - Keep ambiguous and placeholder fields excluded.

4. Remove the unused `HealthTools`/`health_check` MCP implementation, related models, exports, fixtures, and tests unless a real production import or registration proves it is required. Preserve any independent HTTP/Kubernetes readiness endpoint.

5. Update `dev_client.py` to call the two current AS tools with safe example inputs, or delete it if it has no maintained purpose. It must not reference `hello`, `octobot_dummy`, `health_check`, or removed tools.

6. Remove `-p no:cacheprovider` from shared `pyproject.toml`. Keep the valid `asyncio_default_fixture_loop_scope = "function"` setting. For this machine only, run pytest with `-p no:cacheprovider` on the command line if its directory permissions still prevent cache creation.

7. Inspect the actual CI pipeline:
   - If CI runs repository-wide Ruff, mechanically fix all remaining W292 and I001 findings and rerun Ruff until exit code 0.
   - If CI intentionally uses a changed-files lint baseline, document the exact baseline command and prove it exits 0.
   - Do not report a nonzero Ruff command as a passing lint result.

8. Run:
   - the complete pytest suite,
   - the exact CI entrypoint,
   - the applicable Ruff gate,
   - exact MCP tool-inventory verification,
   - generated AS field-contract consistency verification.

Return a factual report separating:
- completed code requirements,
- tests and their exit codes,
- production-release blockers,
- external deployment compatibility names,
- the required human review of the AS output-field mapping.

Do not claim production readiness until the business-name mapping is reviewed and the external Root → AS Specialist → Formatter E2E flow passes.