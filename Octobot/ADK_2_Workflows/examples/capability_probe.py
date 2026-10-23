"""Run with the team's upgraded Executor environment; no model calls occur."""

from __future__ import annotations

import importlib.metadata
import inspect
import json


def main() -> None:
    from google.adk import Agent, Event, Workflow
    from google.adk.workflow import JoinNode, RetryConfig, node

    def entry(node_input: str):
        return Event(route="PASS", output=node_input)

    def complete(node_input: str):
        return Event(output=node_input)

    graph = Workflow(
        name="capability_probe",
        edges=[("START", entry), (entry, {"PASS": complete})],
    )
    agent = Agent(name="probe_agent", mode="single_turn", model="gemini-2.5-flash")
    agent_graph = Workflow(name="agent_graph", edges=[("START", agent)])
    report = {
        "google_adk_version": importlib.metadata.version("google-adk"),
        "conditional_graph_constructed": graph.name,
        "single_turn_agent_graph_constructed": agent_graph.name,
        "join_node_available": JoinNode(name="probe_join").name,
        "node_wrapper_signature": str(inspect.signature(node)),
        "retry_fields": sorted(RetryConfig.model_fields),
        "execution_tested": False,
        "durable_resume_tested": False,
    }
    try:
        task = Agent(name="probe_task", mode="task", model="gemini-2.5-flash")
        Workflow(name="task_graph", edges=[("START", task)])
        report["static_task_agent_supported"] = True
    except (TypeError, ValueError):
        report["static_task_agent_supported"] = False
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
