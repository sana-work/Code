"""Prompt invariants and synthetic payload checks, not live-model finalization tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest
import yaml


ROOT = Path(__file__).resolve().parent
CURRENT = yaml.safe_load((ROOT.parent / "Universal_Chat_Single_Agent_System_Prompt.yaml").read_text())
BASELINE = yaml.safe_load((ROOT / "reports/2026-10-27/finalization-followup/baseline_prompt.yaml").read_text())
SCHEMA = json.loads(CURRENT["output_schema"])
VALIDATOR = Draft202012Validator(SCHEMA)
KEYS = {"status", "intent", "answer", "attributes", "tables", "options", "toolsUsed", "error"}
BUSINESS_TOOLS = {
    "query_as_events_entitlements", "query_tm_current_transactions",
    "query_tm_eod_transactions", "query_tm_settlement_instructions",
}


def payload(status="SUCCESS", error=""):
    return {
        "status": status, "intent": "Answer the enquiry.",
        "answer": "**Summary:** Synthetic evidence only.",
        "attributes": [], "tables": [], "options": [], "toolsUsed": [], "error": error,
    }


def check_prompt_contract(value):
    """Reference check for the prompt's stricter rules; not an executor patch."""
    VALIDATOR.validate(value)
    if set(value) != KEYS:
        raise ValueError("Every final payload needs the eight existing properties")
    status, error = value["status"], value["error"]
    if status not in {"SUCCESS", "NEEDS_CLARIFICATION", "OUT_OF_SCOPE", "FAILED"}:
        raise ValueError("Unsupported status")
    if status == "FAILED":
        if not error.strip() or error == "null":
            raise ValueError("FAILED requires a safe non-empty error string")
    elif error != "":
        raise ValueError("Non-failed error must be exactly the empty string")
    if not set(value["toolsUsed"]).issubset(BUSINESS_TOOLS):
        raise ValueError("Finalization transports do not belong in toolsUsed")


@pytest.mark.parametrize("status", ["SUCCESS", "NEEDS_CLARIFICATION", "OUT_OF_SCOPE"])
def test_non_failed_payload_uses_empty_string_without_schema_change(status):
    value = payload(status)
    assert VALIDATOR.is_valid(value)
    check_prompt_contract(value)


@pytest.mark.parametrize("error", ["TOOL_TIMEOUT", "TOOLS_UNAVAILABLE"])
def test_failed_payload_uses_safe_non_empty_string(error):
    check_prompt_contract(payload("FAILED", error))


@pytest.mark.parametrize("error", [None, "null", " ", "TOOL_TIMEOUT", 0, False, [], {}])
def test_non_failed_error_null_or_non_empty_is_rejected(error):
    with pytest.raises((ValidationError, ValueError)):
        check_prompt_contract(payload(error=error))


@pytest.mark.parametrize("error", [None, "", " ", "null"])
def test_failed_error_cannot_be_null_blank_or_missing_marker(error):
    with pytest.raises((ValidationError, ValueError)):
        check_prompt_contract(payload("FAILED", error))


def test_optional_error_remains_optional_in_ui_schema_but_prompt_initializes_it():
    value = payload()
    del value["error"]
    assert VALIDATOR.is_valid(value)
    assert "error" not in SCHEMA["required"]
    with pytest.raises(ValueError):
        check_prompt_contract(value)


def test_first_screenshot_error_shape_fails_schema_and_corrected_shape_passes():
    errors = list(VALIDATOR.iter_errors(payload(error=None)))
    assert any(list(error.path) == ["error"] and error.validator == "type" for error in errors)
    check_prompt_contract(payload(error=""))


@pytest.mark.parametrize("bad", [json.dumps(payload()), {"schema": payload()}])
def test_transport_arguments_must_be_the_object_not_encoded_or_wrapped(bad):
    assert not VALIDATOR.is_valid(bad)


@pytest.mark.parametrize("tool", ["set_model_response", "finish_task"])
def test_finalization_tools_are_not_reported_as_business_tools(tool):
    value = payload()
    value["toolsUsed"] = [tool]
    with pytest.raises(ValueError):
        check_prompt_contract(value)


def test_literal_null_business_cell_is_not_json_null_and_is_preserved():
    value = payload()
    value["tables"] = [{"id": "table_1", "columns": ["Source text"],
                        "rows": [{"cells": ["null"]}]}]
    value["answer"] += "\n\n**Supporting information**\n\n<<table_1>>"
    before = deepcopy(value)
    check_prompt_contract(value)
    assert value == before


def test_finalizer_and_direct_modes_are_mutually_exclusive_in_prompt():
    instruction = CURRENT["instruction"]
    delivery = instruction.split("FINAL_DELIVERY:", 1)[1].split("\n\n", 1)[0]
    assert "If the runtime registers set_model_response as its final-response transport" in delivery
    assert "call it exactly once" in delivery
    assert "After successful submission, stop immediately" in delivery
    assert "do not call it again, emit a separate direct JSON answer" in delivery
    assert "If set_model_response is not registered, return the complete JSON object directly once" in delivery
    assert "never in the business-call batch or toolsUsed" in delivery
    assert "Do not repeat AS/TM lookups to correct output serialization" in delivery
    assert "Do not call set_model_response" not in instruction


def test_error_rule_has_no_old_omission_instruction():
    instruction = CURRENT["instruction"]
    assert "toolsUsed, and error in every final payload" in instruction
    assert '- error: exactly "" for SUCCESS, NEEDS_CLARIFICATION, and OUT_OF_SCOPE.' in instruction
    assert "For FAILED, use one short safe non-empty code/message" in instruction
    assert "plus error only for FAILED" not in instruction
    assert not re.search(r"omit[^.\n]*\berror\b|error[^.\n]*only for FAILED", instruction)


def test_validation_precedes_delivery_not_a_finalizer_probe():
    instruction = CURRENT["instruction"]
    assert "validate the complete payload before delivery" in instruction
    assert "never in the business-call batch" in instruction
    assert "use finalization as a validation probe" in instruction
    assert "Then use FINAL_DELIVERY once, without a second delivery path" in instruction


@pytest.mark.parametrize("number", [2, 4, 5, 6, 7, 8, 9])
def test_business_grounding_filters_dates_evidence_and_templates_are_unchanged(number):
    pattern = rf"(?ms)^## {number}\. .*?(?=^## \d+\. |\Z)"
    assert re.search(pattern, CURRENT["instruction"]).group() == re.search(pattern, BASELINE["instruction"]).group()


def test_ui_schema_and_runtime_storage_configuration_are_unchanged():
    for key in ("output_schema", "response_type", "output_key"):
        assert CURRENT[key] == BASELINE[key]
    assert hashlib.sha256(CURRENT["output_schema"].encode()).hexdigest() == (
        "c8a46ceac9cc5d2d733778373cec24f4c1cd6a5c2075a6a5a1e7a80f7867a51f"
    )
