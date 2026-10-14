# Testing Agent Protocol

You are the test actor, not the evaluator. For each independent scenario, apply only the supplied tested system instruction, registered synthetic tool definitions, current client message, timestamp, and scenario-specific history/cache. Earlier test scenarios are not client conversation history.

1. Read the full public context for the case. Do not read private fixtures, expected answers, grading rules, or evaluation results.
2. Choose all necessary approved tools, identifiers, filters, limits, and additional registered fields before execution. Write a request array with exactly `name` and `arguments` for each call. Do not call a tool when the tested prompt requires clarification or a direct reply.
3. Dispatch independent calls together. Each tool may run only once per case. Do not retry, repair inputs, request extra fields later, or fetch a second page.
4. Read only the returned evidence. Choose the appropriate display mode and write the final client response. Source arrays may be copied or projected mechanically for fidelity; the actor must choose the mode, fields, and wording itself.
5. Submit exactly one final response object. Save the first attempt unchanged. Do not run the grader or revise after receiving a score.
6. Start the next case with only its supplied context. Report operational problems to the evaluator without inventing a result or marking an unrun case as passed.

The evaluator supplies the case ID and paths for the local harness. Use the `context`, `dispatch`, and `submit` commands documented in README.md. If testing through the API adapter, the adapter delivers tool definitions/results and records the trace automatically.

This protocol is a testing wrapper. It must not be appended to the production chatbot prompt.
