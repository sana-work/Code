# Package Validation

Updated on 23 October 2026.

## Document and Example Checks

- The document, JSON, and Python example use the same generic request-processing scenario.
- The JSON has five nodes with complete exclusive decision routes and one designated terminal node.
- Local Markdown links and code fences are checked.
- Python examples are checked for syntax.
- Superseded domain-specific examples and interaction flows are removed from this revision.

## Diagram Checks

- All three diagrams use deliberate fixed coordinates and orthogonal connectors.
- Node rectangles are checked for overlap and canvas overflow.
- Connector paths are checked for crossings through node rectangles.
- Text is measured and wrapped to fit its intended width.
- SVG and PNG outputs are generated and checked for nonblank image content.
- Each diagram is visually inspected for label placement, directional consistency, and readable spacing.

## Execution Boundary

The upgraded service repositories and their installed ADK environment are not available here. Native graph execution, live model calls, durable PostgreSQL recovery, Kafka behavior, and service-level regression tests have not been run for this documentation revision.

The capability probe is a construction check. The design document specifies the integration and recovery tests required in the actual service environment.
