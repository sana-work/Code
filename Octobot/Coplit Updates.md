Before this implementation can be accepted, address and report the following without adding unrelated abstractions:

1. Identify the authoritative source for `maximum_limit=5000`, `tool_deadline_seconds=55`, and the timeout upper bound of 300 seconds. If no source exists, do not treat them as verified defaults. Use stakeholder-approved environment values and remove any unsupported Python fallback.

2. List every supported environment YAML file and its effective Asset Services tool deadline. Prove that the active environment selects the correct value.

3. Ensure the overall deadline wraps the complete shared execution operation, including validation, request construction, provider execution, retry waits, retries, and response normalization. All retries must share one deadline.

4. Add a deterministic timeout test proving that in-flight work is cancelled, no later retry occurs, and the MCP client receives:
   - status/error status using the existing contract
   - stable code `TOOL_TIMEOUT`
   - `retryable=true`
   - correlation ID
   - message: `The request took longer than the configured time limit. Please try again.`

5. Prove the complete propagation path:
   `MCP ToolResult -> Asset Services Agent -> Formatter Agent -> existing final JSON -> UI`.
   Include the exact redacted objects at every stage. A failed request must not contain a data table or invented records.

6. For both services, provide a table of every registry column showing whether it is filterable, selectable, both, or neither. Confirm that every verified filterable field is represented by an explicit typed tool parameter. Selectable-only fields should be available through `requested_fields`.

7. Obtain stakeholder confirmation for Cash Entitlements having no required filters. Until confirmed, do not production-enable unrestricted Cash Entitlements queries.

8. Derive the maximum limit from existing provider behavior or configuration. Do not retain 5000 merely as an engineering assumption.

9. Run the repository’s actual CI command, full tests, generated MCP-schema inspection, redacted nonproduction smoke tests, Asset Services Agent tests, and formatter/final-schema tests.

10. Return `git status --short`, the complete diff, generated schemas for both tools, test summaries, and all remaining unresolved facts.