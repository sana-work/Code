# ADK 2.x Workflow Design Package

Start with [ADK_2_Workflows.md](ADK_2_Workflows.md). It describes automatic request processing with agentic, deterministic, and decision nodes and maps the required changes to the existing Orchestrator/Executor flow.

For the plain-language explanation, the mixed tool/agent response pattern, and the user-facing drag-and-drop design, read [Workflows Explained and the Visual Builder](Workflow_Explanation_and_Visual_Builder.md).

## Diagrams

- [Platform architecture](diagrams/01-platform-architecture.png): numbered request, transport, execution/response, and persistence bands.
- [Mixed workflow](diagrams/02-example-workflow.png): fetch tool data, run the explanation agent, then compose the response deterministically while the original data bypasses the model.
- [Execution modes](diagrams/03-execution-modes.png): aligned sync, Kafka async, and hybrid columns with a separate SSE delivery explanation.
- [Visual workflow builder](diagrams/04-visual-builder.png): canvas, data bindings, validation, publication, and native execution.

The diagrams use fixed coordinates and orthogonal connectors. Matching SVGs are editable vector outputs. [architecture.mmd](diagrams/architecture.mmd) provides a compact Mermaid overview.

## Examples

- [Mixed native workflow](examples/mixed_response_workflow.py): fetch data, write an introduction with an agent, then emit a deterministic response manifest.
- [Mixed definition](examples/mixed-response-definition.json): matching control edges, data bindings, and final response policy.
- [Composition helper](examples/response_composition.py): exact original-block copying and a scoped fixture store.
- [Composition tests](examples/test_response_composition.py): nine helper tests, independent of ADK/model infrastructure.
- [Secondary branching workflow](examples/native_workflow_example.py) and [definition](examples/workflow-definition.json): either fixed word counting or an agent answer.
- [Capability probe](examples/capability_probe.py): inspect the installed release and construct graphs without a model call.

Run the probe with the Python environment already used by the upgraded Executor:

```bash
python /Users/sanaiqbal/Codes/Code/Octobot/ADK_2_Workflows/examples/capability_probe.py
```

For the primary example, inject a configured model, `ReportTool`, output-store adapter, and trusted execution scope into `mixed_response_workflow.build_workflow(...)`. Run its root in the existing App/Runner setup. Apply `finalize_response(...)` at the last trusted delivery boundary, after every model stage has finished.

The memory output store is a fixture adapter. Async/multi-worker execution needs durable storage and response-boundary integration. Both JSON formats are application proposals that need a compiler/registry, not built-in ADK configuration files.

Run the focused helper tests from this package directory:

```bash
python -m unittest discover -s examples -p test_response_composition.py -v
```

## Diagram Sources

The fixed-layout source is [render_structured_diagrams.cjs](diagrams/render_structured_diagrams.cjs). It uses `sharp` and `@napi-rs/canvas`, resolving the bundled dependencies on this machine when needed.

```bash
node /Users/sanaiqbal/Codes/Code/Octobot/ADK_2_Workflows/diagrams/render_structured_diagrams.cjs
```

Rendering checks node overlaps, canvas boundaries, orthogonal connector paths, connector crossings through boxes, and nonblank output. See [VALIDATION.md](VALIDATION.md) for the package checks and execution boundary.
