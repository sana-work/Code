Paste this into GitHub Copilot with both repositories open in the same workspace:

You are working in a workspace containing two related repositories:

1. **Orchestrator repository**
2. **Executor repository**, which runs agents and tools using Google ADK

Your task is to inspect both repositories and create a code-grounded implementation plan. Do not implement the feature yet.

# Objective

Design a deterministic artifact-materialization mechanism for large tool results such as:

- One or more tables
- Multiple tables returned by different tools
- Large text blocks
- Other tool output that must appear in the final response exactly as returned

Currently, an agent receives tool results, reasons about them, formats its final response according to an output schema, and returns that response through the Executor and Orchestrator.

We want to avoid making the model reproduce large deterministic content. The model should generate the narrative, summary, and surrounding structure while placing validated artifact references where exact tool output belongs. The Executor must later resolve those references and insert the original tool content before the final client-facing response is sent.

# Intended Flow

The target behavior is:

1. A tool executes and returns its result.
2. A Google ADK tool callback identifies fields configured for deterministic passthrough.
3. The complete artifact is stored outside the model context.
4. The callback returns a compact reasoning view to the model containing:
   - Opaque artifact ID
   - Artifact type
   - Column names or structural metadata
   - Row count or content size
   - Safe bounded sample, aggregates, or summary data required for reasoning
   - Placeholder/reference syntax
5. The agent creates its schema-compliant response containing artifact references.
6. After the final model response, the Executor validates the response and resolves each reference.
7. The Executor inserts the exact stored tool content into the appropriate response location.
8. The fully materialized response is validated again.
9. The Executor returns it through the existing Sync, Stream, Async, or Hybrid flow without changing unrelated behavior.

Token reduction is achieved only if the full tool result is not added to subsequent model context. Do not claim token savings if the existing ADK/session flow still sends the raw result to the model.

# Google ADK Integration

Inspect the installed Google ADK version and existing callback/plugin usage before recommending changes.

Evaluate this callback design:

- Use `after_tool_callback` to inspect the successful tool result, store passthrough artifacts, and replace the result seen by the model with a compact reasoning projection.
- Use `on_tool_error_callback` only for artifact-related cleanup or normalized failure metadata where appropriate.
- Use a final-event callback such as plugin-level `on_event_callback`, if supported by the installed ADK version, to materialize only the terminal response before client delivery.
- Do not rely on `after_agent_callback` for complete response replacement unless the installed ADK version explicitly supports it.
- Evaluate `after_model_callback` only as a fallback and explain its session-history and context-size consequences.
- If the existing Executor response boundary is safer than an ADK final-event callback, recommend callback-based artifact capture plus Executor-owned terminal materialization.
- Account for callback ordering and short-circuit behavior. Existing logging, audit, streaming, or `DbLoggerPlugin` behavior must not be skipped accidentally.

Prefer a focused component such as `DeterministicArtifactPlugin` or equivalent, backed by separate storage, projection, validation, and rendering services. Match the repository’s existing patterns instead of introducing a new framework unnecessarily.

# Artifact Contract

Evaluate a structured contract instead of unrestricted string replacement.

A possible internal reference is:

```json
{
  "artifact_id": "art_opaque_id",
  "kind": "table",
  "content_type": "application/json"
}
```

A model-visible placeholder could be:

```text
{{artifact:art_opaque_id}}
```

The final design must support multiple artifacts from multiple tools and define:

- Stable opaque IDs
- Artifact type
- Tool-call ID
- Runtime, invocation, session, user, and tenant ownership
- MIME/content type
- Size and row limits
- Checksum or integrity metadata
- Creation and expiry time
- Rendering mode
- Ordering
- Duplicate-reference behavior
- Missing-reference behavior
- Unreferenced-artifact cleanup
- Whether the same artifact may be referenced more than once

Determine whether the current response schema should use:

1. Placeholders inside an answer template
2. A structured `artifacts` or `tables` map
3. Typed content blocks
4. A backward-compatible combination

Prefer structured references where possible. If text replacement is required for compatibility, require exact one-pass replacement with no recursive expansion.

# Storage Requirements

Inspect existing storage and persistence services before proposing anything new.

For Sync and ordinary Stream execution, an invocation-scoped store may be sufficient only when the artifact is needed until the terminal response is assembled.

For Async, Hybrid, Resume, retries, or process restarts, artifacts must use durable storage. Evaluate:

- Existing tenant-routed database or result storage
- Existing object/blob storage
- Google ADK `ArtifactService`
- A repository-specific artifact service abstraction backed by existing infrastructure

Do not recommend in-memory storage for durable modes.

The plan must define retention, cleanup, encryption, tenant isolation, authorization, result-size limits, and behavior when storage or materialization fails.

# Reasoning Projection

The model may need enough information to summarize or reason about a table without receiving every row.

Define how the Executor will construct a bounded reasoning projection, potentially containing:

- Schema and column descriptions
- Row count
- Selected aggregates
- First/last rows
- Relevant filtered rows
- Tool-produced summary
- Truncation metadata

Do not assume a small sample is sufficient for every question. Identify cases requiring deterministic aggregation, an additional query/tool call, or access to more rows.

# Existing-Code Investigation

Inspect both repositories before writing the plan. Locate and document the actual files and symbols responsible for:

- Agent creation and Google ADK configuration
- Tool registration and execution
- Existing ADK callbacks and plugins
- `DbLoggerPlugin` or equivalent lifecycle callbacks
- Output schema and structured-response parsing
- Agent and tool events
- Executor request handling
- Terminal response preparation
- Executor-to-Orchestrator contracts
- Sync coordination
- Client-facing SSE streaming
- Async and Hybrid background execution
- Runtime persistence and resume
- Authentication, tenant routing, and redaction
- Tests covering tool results and final responses

Treat the current code as authoritative. Correct any assumptions in this prompt when the implementation differs.

Use exact repository-relative paths and symbol names in `plan.md`. Distinguish clearly between:

- Existing behavior
- Required modifications
- New components
- Optional future improvements

# Scope and Change Discipline

- Do not modify application source code.
- Do not add dependencies.
- Do not change configuration or lock files.
- Do not perform unrelated refactoring.
- Only create or update `plan.md` at the common workspace root.
- Keep proposed implementation changes minimal and consistent with current code structure.
- Reuse existing services, models, callbacks, validation, and persistence patterns where appropriate.
- Do not silently change existing endpoint contracts.
- Preserve current non-stream behavior.
- Separate the initial Sync/Stream implementation from later Async/Hybrid support if that reduces risk.

# Required `plan.md` Structure

Create `plan.md` with these sections:

1. Executive summary
2. Problem statement and goals
3. Non-goals
4. Current code findings
5. Current end-to-end data flow
6. Recommended architecture
7. Google ADK callback integration
8. Artifact and placeholder contract
9. Storage and lifecycle
10. Response materialization and schema validation
11. Security, redaction, and tenant isolation
12. Behavior by Sync, Stream, Async, Hybrid, and Resume mode
13. Repository-by-repository file impact
14. Step-by-step implementation phases
15. Tests and validation required after every phase
16. Failure scenarios and recovery behavior
17. Observability and metrics
18. Backward compatibility and rollout
19. Alternatives considered
20. Risks, open questions, and recommended defaults
21. Acceptance criteria

Include clean Mermaid sequence diagrams for:

- Tool execution through artifact capture and model reasoning
- Final response materialization
- Stream delivery
- Future Hybrid disconnect, persistence, and later retrieval

Keep Mermaid node text short so labels and arrows do not overlap.

# Testing Expectations

For every implementation phase, identify the exact tests and commands that should be run. Include coverage for:

- No-artifact responses
- One table
- Multiple tables from one tool
- Multiple tables from multiple tools
- Large text artifacts
- Repeated references
- Missing and unauthorized references
- Wrong artifact type
- Expired artifacts
- Oversized artifacts
- Tool failure after partial storage
- Materialization failure
- Output-schema failure before and after materialization
- Redaction of sensitive tool input/output
- Callback ordering
- Model receives only the compact reasoning projection
- Existing JSON and streaming route regressions
- Client disconnect and cancellation
- Async/Hybrid retry and idempotency where applicable

# Final Instruction

Create the completed plan at:

```text
plan.md
```

Do not implement the feature. After creating the file, report:

- The path to `plan.md`
- The repositories and major files inspected
- The recommended integration point
- Any blocking uncertainty discovered in the current code