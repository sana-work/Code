Proceed with Phase 1 under these decisions:

1. Cross-repository Phase 1 is approved. Keep artifact capture and compact session history in the Executor. Perform materialization only at the true external boundary in `orchestration/service/execution_response_builder.py::build_execution_response()`, after all LLM synthesis. Cover all three response branches. Nothing passed into `prepare_response()` or another model may contain materialized artifact bytes.

2. Use fail-closed behavior for artifact isolation. If capture or durable storage fails, do not pass the raw large result to the model. Return a bounded, sanitized error using the repository’s existing tool-error shape and retry semantics. Do not expose payload data, storage details, or artifact identifiers. The artifact subsystem should not cause an unhandled HTTP 500.

3. Add a dedicated `enable_artifact_capture` opt-in flag, independent of `enable_audit_context_logging`, defaulting to `False`. Implementation and disabled-by-default testing may proceed now. Production enablement requires separate security/data-retention approval.

Additional requirements:

- Preserve the confirmed plugin order and make `ArtifactCapturePlugin` skip every result whose existing `isError` flag is true.
- Before materializer implementation, prove that the Orchestrator has enough authenticated tenant, use-case, and session context to resolve artifact references securely. Reuse existing tenant-routed storage access. Do not duplicate capture logic or introduce an unreviewed public endpoint.
- Keep compact `llm_context` and `artifact_refs` through Executor responses, Orchestrator step outputs, and `prepare_response()` synthesis.
- Materialize only the final response returned by `build_execution_response()`.
- Do not implement Async, Hybrid, Resume, `query_artifact`, aggregation, cleanup jobs, or AG-UI rendering in Phase 1.
- Add tests for every `build_execution_response()` branch, proving:
  - synthesis receives no artifact bytes;
  - final materialization is exact;
  - unauthorized or invalid references are not expanded;
  - feature-flag-off behavior is unchanged;
  - Executor ADK history contains only compact context and references;
  - error tool results are never captured.
- Use the confirmed workspace-root virtual environment for Executor tests.
- Run focused tests after each change, then adjacent suites and both repositories’ complete affected suites.
- Stop after Phase 1 and provide the required implementation and test report before beginning Phase 2.