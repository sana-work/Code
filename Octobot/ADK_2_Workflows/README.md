# ADK 2.x Workflow Design Package

Start with [ADK_2_Workflows.md](ADK_2_Workflows.md). It describes automatic request processing with agentic, deterministic, and decision nodes and maps the required changes to the existing Orchestrator/Executor flow.

## Diagrams

- [Platform architecture](diagrams/01-platform-architecture.png): numbered request, transport, execution/response, and persistence bands.
- [Generic workflow](diagrams/02-example-workflow.png): a request branches to either fixed code or one agent and converges on a common response formatter.
- [Execution modes](diagrams/03-execution-modes.png): aligned sync, Kafka async, and hybrid columns with a separate SSE delivery explanation.

The diagrams use fixed coordinates and orthogonal connectors. Matching SVGs are editable vector outputs. [architecture.mmd](diagrams/architecture.mmd) provides a compact Mermaid overview.

## Examples

- [Native Python workflow](examples/native_workflow_example.py): normalize a bounded text request, choose a route, count words or run an agent, and format one output.
- [Application definition](examples/workflow-definition.json): the matching proposed five-node JSON definition.
- [Capability probe](examples/capability_probe.py): inspect the installed release and construct graphs without a model call.

Run the probe with the Python environment already used by the upgraded Executor:

```bash
python /Users/sanaiqbal/Codes/Code/Octobot/ADK_2_Workflows/examples/capability_probe.py
```

To use the sample, call `build_workflow(model)` with the configured model/provider, use the returned root in the existing App/Runner setup, and send `EXAMPLE_INPUT` as text through the installed public input API. Use a native session scoped to that workflow run.

The deterministic example requires no external business service. The agentic branch requires the normal configured model environment. The JSON is an application proposal that needs a compiler/registry; it is not a built-in ADK configuration file.

## Diagram Sources

The fixed-layout source is [render_structured_diagrams.cjs](diagrams/render_structured_diagrams.cjs). It uses `sharp` and `@napi-rs/canvas`, resolving the bundled dependencies on this machine when needed.

```bash
node /Users/sanaiqbal/Codes/Code/Octobot/ADK_2_Workflows/diagrams/render_structured_diagrams.cjs
```

Rendering checks node overlaps, canvas boundaries, orthogonal connector paths, connector crossings through boxes, and nonblank output. See [VALIDATION.md](VALIDATION.md) for the package checks and execution boundary.
