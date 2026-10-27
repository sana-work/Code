"""Tool -> agent -> deterministic composition, with original data bypass.

This factory emits a manifest. The platform's final response adapter calls
response_composition.finalize_response after every model stage has finished.
The injected output store must be durable for multi-worker/recovery operation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from google.adk import Agent, Context, Event, Workflow
from google.adk.workflow import node
from pydantic import BaseModel, ConfigDict, Field

from native_workflow_example import validate_payload
from response_composition import (
    ExecutionScope,
    OriginalOutputRef,
    OriginalOutputStore,
    compose_manifest,
)


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    report_name: str = Field(min_length=1, max_length=128)


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=4000)
    status: Literal["success"]
    row_count: int = Field(ge=0)


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(min_length=1, max_length=4000)


@dataclass(frozen=True)
class ToolReport:
    original_bytes: bytes
    row_count: int
    content_type: str = "text/plain; charset=utf-8"


class ReportTool(Protocol):
    async def fetch(self, scope: ExecutionScope, request: ReportRequest) -> ToolReport: ...


def build_workflow(
    model: Any,
    tool: ReportTool,
    store: OriginalOutputStore,
    scope: ExecutionScope,
) -> Workflow:
    @node(name="normalize")
    def normalize(node_input: Any):
        request = validate_payload(node_input, ReportRequest)
        return Event(output=request.model_dump(mode="json"))

    @node(name="fetch")
    async def fetch(node_input: ReportRequest):
        report = await tool.fetch(scope, node_input)
        safe_input = AgentInput(
            question=node_input.question, status="success", row_count=report.row_count
        )
        ref = store.put(scope, report.original_bytes, report.content_type)
        return Event(
            output=safe_input.model_dump(mode="json"),
            state={"original_output_ref": asdict(ref)},
        )

    explain = Agent(
        name="explain",
        model=model,
        mode="single_turn",
        input_schema=AgentInput,
        output_schema=Explanation,
        instruction=(
            "Write a brief introduction for the requested report. You know its "
            "status and row count only. Do not invent row values, totals or "
            "patterns. The original data will be appended by application code. "
            "Return only the declared explanation structure."
        ),
    )

    @node(name="compose")
    def compose(ctx: Context, node_input: Any):
        narrative = validate_payload(node_input, Explanation)
        ref = OriginalOutputRef(**ctx.state["original_output_ref"])
        return Event(output=asdict(compose_manifest(narrative.explanation, ref)))

    return Workflow(
        name="generic_report_response_v1",
        edges=[("START", normalize, fetch, explain, compose)],
    )
