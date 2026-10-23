"""Generic native ADK workflow: fixed code or an agent handles a text request.

Construct a fresh root using the platform's configured model, then execute it
through the existing App/Runner and run-scoped session service.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from google.adk import Agent, Context, Event, Workflow
from google.adk.workflow import node
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestData(StrictModel):
    request_type: Literal["RULE_BASED", "REASONING"]
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Request text must contain non-whitespace characters")
        return value


class NodeAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=4000)


class RequestOutput(StrictModel):
    answer: str
    processing_type: Literal["RULE_BASED", "REASONING"]
    data: dict[str, int] = Field(default_factory=dict)


def validate_payload(value: Any, schema: type[BaseModel]) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif hasattr(value, "parts"):
        parts = value.parts or []
        if any(getattr(part, "text", None) is None for part in parts):
            raise ValueError("This example accepts text JSON input only")
        value = "".join(part.text for part in parts)
    if isinstance(value, str):
        return schema.model_validate_json(value)
    return schema.model_validate(value)


def build_workflow(model: Any) -> Workflow:
    @node(name="normalize")
    def normalize(node_input: Any):
        request = validate_payload(node_input, RequestData)
        payload = request.model_dump(mode="json")
        return Event(
            output=payload,
            state={"request_context": payload, "request_metrics": {}},
        )

    @node(name="route")
    def route(node_input: RequestData):
        return Event(
            route=node_input.request_type,
            output=node_input.model_dump(mode="json"),
        )

    @node(name="rules")
    def rules(node_input: RequestData):
        count = len(node_input.text.split())
        answer = NodeAnswer(answer=f"The request contains {count} words.")
        return Event(
            output=answer.model_dump(mode="json"),
            state={"request_metrics": {"word_count": count}},
        )

    agent = Agent(
        name="agent",
        model=model,
        mode="single_turn",
        input_schema=RequestData,
        output_schema=NodeAnswer,
        instruction=(
            "Handle the supplied text request. For a summarization request, "
            "summarize only the supplied text. Return the declared answer "
            "schema and do not invent facts."
        ),
    )

    @node(name="respond")
    def respond(ctx: Context, node_input: Any):
        answer = validate_payload(node_input, NodeAnswer)
        request = RequestData.model_validate(ctx.state["request_context"])
        output = RequestOutput(
            answer=answer.answer,
            processing_type=request.request_type,
            data=ctx.state.get("request_metrics", {}),
        )
        return Event(output=output.model_dump(mode="json"))

    return Workflow(
        name="generic_request_processing_v1",
        max_concurrency=1,
        edges=[
            ("START", normalize, route),
            (route, {"RULE_BASED": rules, "REASONING": agent}),
            (rules, respond),
            (agent, respond),
        ],
    )


EXAMPLE_INPUT = json.dumps(
    {"request_type": "RULE_BASED", "text": "Count the words in this request"}
)
