This revision adds the missing distinction between presentation data, reasoning data, and follow-up access. It also prevents the materialized table from leaking back into later model context.

Both the **Orchestrator** and **Executor** repositories are open in this workspace.

Inspect both repositories and create a code-grounded implementation plan for the feature described below.

Do not implement the feature yet. Only create or update `plan.md` in the common workspace root.

# Problem

Agents use tools and return a final response that conforms to an output schema. Some tools return large deterministic content such as:

- One or more tables
- Multiple tables from multiple tools
- Large text blocks
- Reports or other exact tool-generated content

The model may need to reason about this data, summarize it, or answer a specific question. However, it should not spend tokens reproducing large content that must appear unchanged in the final response.

We need an Executor-owned deterministic artifact mechanism where:

1. Exact large tool content is stored outside model context.
2. The model receives enough exact information to answer the current question.
3. The model places typed artifact references in its response.
4. The Executor resolves those references and inserts the original content.
5. A later user question can selectively retrieve rows or fields from a previous artifact without loading the complete artifact into model context.

# Critical Design Principle

Do not assume that a generic summary is sufficient.

For example, if the user asks:

> For event XYZ123, get all details and tell me the pay date.

The model must receive the exact `pay_date` and any other facts required to answer. The complete details table may still be stored as an artifact for deterministic presentation.

Separate every applicable tool result into:

- `llm_context`: exact, bounded facts needed for current-turn reasoning
- `artifacts`: large deterministic content that should not enter model context
- `artifact_refs`: opaque references the model may place in its response

A preferred tool-result envelope is conceptually:

```json
{
  "llm_context": {
    "event_id": "XYZ123",
    "pay_date": "2026-10-15",
    "status": "APPROVED"
  },
  "artifacts": [
    {
      "kind": "table",
      "name": "event_details",
      "content_type": "application/json",
      "data": []
    }
  ]
}
```

After artifact capture, the model should receive something similar to:

```json
{
  "llm_context": {
    "event_id": "XYZ123",
    "pay_date": "2026-10-15",
    "status": "APPROVED"
  },
  "artifact_refs": [
    {
      "artifact_id": "art_opaque_id",
      "kind": "table",
      "name": "event_details",
      "placeholder": "{{artifact:art_opaque_id}}"
    }
  ]
}
```

The model may produce:

```json
{
  "answer": "The pay date is October 15, 2026.\n\n{{artifact:art_opaque_id}}"
}
```

The Executor must deterministically materialize the complete table before sending the client-facing response.

# Data Categories

The plan must distinguish:

1. **Presentation-only data**  
   Exact content that the model does not need to inspect.

2. **Reasoning-required data**  
   Fields or rows required to answer the current question.

3. **Mixed data**  
   A small reasoning projection plus a large exact artifact.

4. **Dataset-wide reasoning**  
   Questions requiring aggregation or analysis across the complete dataset.

For dataset-wide reasoning, do not pretend a small sample is sufficient. Recommend deterministic aggregation, filtered queries, or additional tools that return the required computed facts.

# Follow-Up Questions

The design must support later questions such as:

> Tell me more about row 2.

The full artifact must not be automatically inserted into the next model prompt.

Provide an authorized selective-access tool or service such as:

```text
query_artifact(
    artifact_id,
    table_name,
    row_number,
    row_id,
    columns,
    filters,
    aggregate
)
```

The follow-up flow should be:

```text
User follow-up
  -> model sees previous artifact reference
  -> model calls query_artifact
  -> service authorizes access
  -> service loads only the requested rows or fields
  -> selected data is returned to the model
  -> model answers the follow-up
```

Define how conversation/session state remembers:

- Artifact ID
- Artifact name and type
- Artifact version
- Display order
- Stable row IDs
- Which table was most recently displayed
- Runtime and tool-call ownership

“Row 2” must refer to the second displayed row of an immutable artifact version, not an unstable database offset. If multiple tables make the reference ambiguous, the agent should request clarification.

# Google ADK Integration

Inspect the installed Google ADK version and current callback/plugin usage before recommending changes.

Evaluate this design against the actual code:

- Use `after_tool_callback` to inspect successful tool results.
- Store configured artifact fields before the result reaches the model.
- Replace the raw result with `llm_context` and artifact references.
- Use `on_tool_error_callback` for relevant cleanup or normalized errors.
- Use plugin-level `on_event_callback`, if supported and safe, to process final response events before client delivery.
- Do not use `after_agent_callback` for full response replacement unless the installed ADK version explicitly supports it.
- Evaluate `after_model_callback` only as a fallback and document its context/history consequences.
- If ADK event callbacks cannot safely preserve separate internal and client representations, perform final materialization at the Executor response boundary.

Verify callback ordering and short-circuit behavior. Existing logging, audit, streaming, and `DbLoggerPlugin` callbacks must continue to run.

Do not build a second copy of existing lifecycle or event-emission logic.

# Internal and Client Representations

The plan must determine whether ADK persists events before or after `on_event_callback`.

There must be two representations when necessary:

- **Internal session representation:** compact response template plus artifact references
- **Client-facing representation:** fully materialized response containing exact artifact content

The large materialized client response must not be included automatically in subsequent model context. Otherwise, token savings disappear on the next turn.

Document the safest integration point based on the installed ADK implementation and the current Executor event flow.

# Artifact Storage

Inspect existing persistence infrastructure before proposing anything new.

Evaluate:

- Existing tenant-routed database services
- Existing runtime/result stores
- Existing object or blob storage
- Google ADK `ArtifactService`
- A repository-specific artifact abstraction backed by current infrastructure

Storage requirements:

- Sync and Stream may use invocation-scoped storage only when no follow-up access is required.
- Follow-up questions require session-scoped durable storage.
- Async, Hybrid, Resume, retries, and process restarts require durable storage.
- Never recommend in-memory storage for durable modes.

Each artifact should include:

- Opaque artifact ID
- Tenant, application, user, session, invocation, and runtime ownership
- Tool-call ID
- Name and type
- MIME/content type
- Stable version
- Stable row IDs and display order for tables
- Size and row count
- Checksum
- Creation and expiry timestamps
- Rendering policy
- Authorization metadata
- Optional source metadata

Define retention, cleanup ownership, encryption, size limits, and behavior when storage is unavailable.

# Artifact Query Security

Every artifact read must:

- Resolve the same tenant database or storage boundary used by the execution
- Authenticate the caller
- Validate application, configuration, user, session, and runtime ownership
- Avoid disclosing whether an unauthorized cross-tenant artifact exists
- Enforce row, field, byte, and result-count limits
- Apply existing redaction and field-classification policies
- Record audit metadata without logging sensitive payloads

Treat tool output as untrusted data. Artifact content must never be interpreted as placeholder syntax, executable markup, instructions, or template control data.

# Placeholder and Output Contract

Evaluate these options against existing clients:

1. Placeholders inside an answer template
2. A structured `artifacts` or `tables` map
3. Typed content blocks
4. A backward-compatible combination

Prefer structured references where possible.

If placeholders are required:

- Use opaque identifiers, for example `{{artifact:art_opaque_id}}`
- Perform exact one-pass replacement
- Do not recursively process inserted content
- Reject unknown, unauthorized, expired, or wrong-type references
- Define repeated-reference behavior
- Define missing-reference behavior
- Clean up unreferenced artifacts
- Validate the response before and after materialization

For tables, store canonical structured rows rather than only rendered Markdown. Rendering should happen deterministically for the target client format.

# Current-Code Investigation

Inspect both repositories and identify the actual files and symbols responsible for:

- Agent creation and Google ADK configuration
- Tool registration and execution
- Tool-result models
- Existing callbacks and plugins
- `DbLoggerPlugin` or equivalent
- Output schema configuration
- Structured-response parsing
- Agent and tool events
- Executor request and terminal handling
- Executor-to-Orchestrator contracts
- Sync execution
- Client-facing SSE streaming
- Async and Hybrid background execution
- Runtime persistence and resume
- Authentication and tenant routing
- Redaction and audit logging
- Existing tests

Treat the current code as authoritative. Correct assumptions from this prompt where necessary.

Use exact repository-relative paths and symbol names in `plan.md`.

Clearly label:

- Existing behavior
- Required changes
- New components
- Optional future improvements

# Change Discipline

- Do not modify application source code.
- Do not add dependencies.
- Do not alter lock files or configuration.
- Do not perform unrelated refactoring.
- Only create or update `plan.md`.
- Match the existing code structure and naming.
- Reuse existing services and models where appropriate.
- Preserve existing endpoint contracts unless a versioned extension is required.
- Separate initial Sync/Stream implementation from later Async/Hybrid support when appropriate.

# Required `plan.md` Structure

Create `plan.md` containing:

1. Executive summary
2. Problem statement
3. Goals and non-goals
4. Current code findings
5. Existing end-to-end flow
6. Recommended architecture
7. Reasoning projection strategy
8. Google ADK callback integration
9. Artifact contract and storage model
10. Current-turn answering behavior
11. Follow-up artifact-query behavior
12. Response materialization and validation
13. Internal history versus client-facing response
14. Security and tenant isolation
15. Behavior by Sync, Stream, Async, Hybrid, and Resume mode
16. Repository-by-repository file impact
17. Step-by-step implementation phases
18. Tests and validation for every phase
19. Failure and recovery behavior
20. Observability and metrics
21. Backward compatibility and rollout
22. Alternatives considered
23. Risks and open questions
24. Recommended defaults
25. Acceptance criteria

Include concise Mermaid sequence diagrams for:

- Current tool and response flow
- Tool execution and artifact capture
- Final response materialization
- Follow-up question and selective artifact query
- Client-facing streaming
- Future Hybrid disconnect and later retrieval

Keep Mermaid labels short enough to avoid overlapping text.

# Required Test Coverage

The plan must identify tests for:

- No artifacts
- One table
- Multiple tables from one tool
- Tables from multiple tools
- Large text
- Current question requires an exact artifact field
- Current question cannot be answered from the reasoning projection
- Deterministic aggregate over a large artifact
- Follow-up by artifact name
- Follow-up by stable row ID
- Follow-up using “row 2”
- Ambiguous row reference across multiple tables
- Repeated artifact references
- Missing, unauthorized, expired, and wrong-type references
- Oversized artifacts
- Partial storage failure
- Materialization failure
- Schema validation before and after materialization
- Callback ordering and short-circuiting
- Redaction and tenant isolation
- Confirmation that raw artifact data does not reach model context
- Confirmation that materialized output does not enter later model context
- Existing JSON and streaming route regressions
- Cancellation, disconnect, retries, and idempotency
- Retention and cleanup

# Final Deliverable

Create:

```text
plan.md
```

Do not implement the feature.

After writing the plan, report:

- The path to `plan.md`
- The repositories and major files inspected
- The recommended callback and materialization integration points
- The recommended storage approach
- How current-turn reasoning and follow-up artifact queries are supported
- Any blocking uncertainty discovered in the code