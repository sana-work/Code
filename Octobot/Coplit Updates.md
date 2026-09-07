Perform a final acceptance audit of the current working tree. Inspect the actual implementation and tests; do not rely on your previous completion summary.

Required corrections:

1. Production tool discovery must expose exactly:
   - `query_as_events_entitlements`
   - `query_as_cash_entitlements`

   Remove `octobot_dummy` and every obsolete discovery or generic provider tool from production registration. Add an exact tool-inventory test.

2. Finish the generic naming cleanup:
   - No `ApigeeService`, `ApigeeEnvironment`, `apigee_service`, or other Apigee-branded internal symbols.
   - Use generic provider API names throughout application code, tests, README, and active architecture documents.
   - If an external Helm, Vault, URL, or environment contract cannot yet be renamed, isolate it in one compatibility boundary. Do not spread the legacy name through generic modules. Clearly document every retained external identifier and why changing it would break deployment.
   - Update or mark the old implementation document as superseded.

3. Re-audit filter security. Percent encoding alone is not proof of safe provider-filter serialization because the server normally decodes URL parameters before parsing the filter language.
   - Inspect the final outgoing HTTP request.
   - Test values containing `A>=B`, commas, ampersands, percent escapes, quotes, equals signs, whitespace, and attempted query-parameter injection.
   - Verify behavior after the same decoding performed by the provider.
   - Do not manually encode values and then accidentally encode them again in the HTTP client.
   - If the provider grammar cannot safely represent a value, reject it with `INVALID_PARAMS` until the grammar is verified.

4. Do not describe `400000` as an authoritative upstream limit unless a repository source or provider contract proves it. Separate the provider transport limit from the much smaller agent-facing result limit. If no approved agent limit exists, flag that decision instead of inventing one.

5. Remove `safe_account` length constraints unless an authoritative source establishes them. Retain only verified rules: it is a string, digits only, and leading zeroes are preserved exactly.

6. Verify the generic runtime:
   - Maps provider columns to business-facing output field names.
   - Never exposes portable IDs, raw provider columns, URLs, credentials, or unrestricted provider error payloads.
   - All errors use the normalized response envelope.
   - Provider details are allowlisted.
   - `asyncio.CancelledError` is re-raised.
   - Expected validation, transport, timeout, malformed-response, and unexpected failures are handled safely.
   - Invalid limits and offsets are rejected, never clamped.

7. Produce a traceability table for every exposed AS input and output field showing:
   - business name,
   - provider column,
   - authoritative source,
   - required/optional status,
   - aliases,
   - validation applied.

8. Integrate and test the three-agent flow:
   - root orchestrator,
   - Asset Services specialist,
   - final response formatter.

   The AS specialist must have access only to the two AS tools. TM must remain explicitly unavailable until added later.

9. Run the full test suite and lint all changed files. Add end-to-end tests covering:
   - successful events request,
   - successful cash request,
   - clarification for missing required input,
   - invalid identifier,
   - malicious filter value,
   - invalid pagination,
   - provider error,
   - timeout,
   - root routing,
   - formatter output,
   - exact tool inventory.

Return a concise report containing changed files, deleted legacy files, exact test commands and results, remaining legacy-name matches, and unresolved external decisions. Do not claim completion while any acceptance item remains unresolved.