Continue the final cleanup. Do not claim full completion until every item below is satisfied.

Decisions for the initial Asset Services release:

- MCP input and output field keys use `snake_case`.
- The provider column `SfAcntNm` maps to the agent-facing key `safe_account` in both tools.
- The agent-facing maximum result size is 100 records per call. Pagination remains available through `offset`.
- `400000` remains only an internal, explicitly unverified provider transport ceiling.
- Only equality filters are supported.
- Reject commas in single-value filters with `INVALID_PARAMS` until the real provider grammar is verified.
- External `APIGEE_`/Helm/Vault names may remain only inside the documented compatibility boundary.

Required changes:

1. Remove runtime generation of agent-facing output names from `english_name`.
2. Create an explicit, immutable, reviewed business-name-to-provider-column mapping for each AS tool.
3. Validate every mapping against the service registry at startup.
4. Never use provider column names or abbreviations as collision suffixes.
5. For duplicate or ambiguous English names, define a meaningful explicit business key. If no authoritative name is available, do not expose that field yet.
6. Use `safe_account` consistently for `SfAcntNm`; do not emit `safekeeping_number`.
7. Remove the `MAXIMUM_LIMIT` compatibility alias if no external caller uses it.
8. Enforce the 100-record agent limit in the generated tool schema and runtime. Keep the provider transport limit separate.
9. Delete all unused `SampleDomainService`, `SampleDomainTools`, related exports, fixtures, and tests. Preserve a deployment health endpoint only if it is independently required.
10. Update `Octobot_MCP_API_Function_Flow.md` to document:
    - the current two-tool AS release,
    - snake_case MCP contracts,
    - the actual module layout,
    - the generic shared runtime,
    - TM as a future extension,
    - the external Root/AS/Formatter prompt pipeline.
11. Generate a complete checked-in AS field-contract artifact containing every exposed input and output:
    - business key,
    - provider column,
    - source,
    - required/optional status,
    - aliases,
    - validation,
    - default-output status.
12. Print the two pytest warnings and fix them. A narrowly scoped warning suppression is allowed only when the warning is proven to originate from an external dependency and includes a comment explaining why.
13. Add tests proving:
    - exactly two MCP tools are registered,
    - output enums contain only explicit approved business keys,
    - no generated key contains a provider abbreviation,
    - both tools return `safe_account`,
    - limits above 100 are rejected rather than clamped,
    - comma-containing filters are rejected,
    - equality-filter values cannot alter the column or query parameters,
    - no SampleDomain imports or registrations remain.

Run the full tests and lint checks. Return exact results, warnings, remaining legacy-name matches, exact tool-schema snapshots, and the complete list of unresolved external decisions.