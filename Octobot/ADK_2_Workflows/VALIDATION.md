# Package Validation

Updated on 23 October 2026.

## Document and Example Checks

- The primary document, definition, Python factory, and diagram use tool fetch -> explanation agent -> deterministic composition.
- The mixed definition has four nodes with a terminal composer and explicit private/safe data bindings.
- The secondary branching definition retains five nodes and complete exclusive decision routes.
- Local Markdown links and code fences are checked.
- Python examples are checked for syntax.
- Nine composition-helper tests passed: byte preservation, non-ASCII/whitespace preservation, manifest references, cross-tenant/run denial, checksum mismatch, changed payload, missing reference, and size bounds.

## Diagram Checks

- All four diagrams use deliberate fixed coordinates and orthogonal connectors.
- Node rectangles are checked for overlap and canvas overflow.
- Connector paths are checked for crossings through node rectangles.
- Text is measured and wrapped to fit its intended width.
- SVG and PNG outputs are generated and checked for nonblank image content.
- Each diagram is visually inspected for label placement, directional consistency, and readable spacing.

## Execution Boundary

The upgraded service repositories and their installed ADK environment are not available here. Native graph execution, live model calls, durable PostgreSQL recovery, Kafka behavior, and service-level regression tests have not been run for this documentation revision.

The focused tests execute only the composition/store helper. They do not prove that a live model prompt excludes original data; that requires the model-request and later-synthesis integration tests described in the guide. The fixture memory store cannot survive process restart or serve different workers.

The capability probe is a construction check. The design document specifies the integration and recovery tests required in the actual service environment.
