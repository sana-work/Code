"""Finite reference-policy and static prompt checks; no live agent/latency trial."""
from copy import deepcopy
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
import pytest
import yaml

from fixtures import AS, CURRENT, EOD, SI, DEFAULT_FIELDS, FIELD_INFO
from harness import tool_spec as historical_tool_spec
from field_selection_policy import (
    evidence_mode, mock_result, needs_lookup, plan_fields, presentation_table,
    required_headers, tool_spec, validate_presentation,
)


ROOT = Path(__file__).resolve().parent
PROMPT = yaml.safe_load((ROOT.parent / "Universal_Chat_Single_Agent_System_Prompt.yaml").read_text())
BASELINE = yaml.safe_load((ROOT / "reports/2026-10-27/baseline_prompt.yaml").read_text())


def section(instruction, number):
    return re.search(rf"(?ms)^## {number}\. .*?(?=^## \d+\. |\Z)", instruction).group()


def source_table(name=AS, rows=1):
    fields = list(FIELD_INFO[name])
    values = {field: f"source-{i}" for i, field in enumerate(fields)}
    values.update(event_id="0001000001", account_id="00123456", isin="SYNTHETIC0001",
                  payment_date="2026-01-01 00:00:00.000", currency="USD",
                  payment_status="PAID", cash_amount="100.00", tax_amount="0", security_name="null",
                  narrative='null grandson, "quoted" | \\ line\nnext \u00e9',
                  record_date="", timestamp="2026-01-01T00:00:00.001Z")
    return {
        "columns": [FIELD_INFO[name][field]["label"] for field in fields],
        "rows": [{"cells": [values[field] for field in fields]} for _ in range(rows)],
    }


def case(name=AS, rows=1):
    return {"fixtures": {name: {"status": "SUCCESS", "table": source_table(name, rows)}}}


@pytest.mark.parametrize("arguments", [
    {"event_id": "0001000001"},
    {"event_id": "0001000001", "requested_fields": []},
    {"event_id": "0001000001", "requested_fields": ["*"]},
    {"event_id": "0001000001", "requested_fields": ["lake_timestamp"]},
    {"event_id": "0001000001", "requested_fields": ["cash_amount", "cash_amount"]},
])
def test_as_rejects_absent_empty_unregistered_or_duplicate_projection(arguments):
    assert mock_result(case(), AS, arguments)["status"] == "ERROR"


def test_input_filter_schema_is_unchanged():
    old = deepcopy(historical_tool_spec(AS)["parameters"])
    new = deepcopy(tool_spec(AS)["parameters"])
    old["properties"].pop("requested_fields")
    new["properties"].pop("requested_fields")
    new.pop("required")
    assert new == old


def test_filter_does_not_imply_returned_identifier_or_other_defaults():
    result = mock_result(case(), AS, {
        "event_id": "0001000001", "account_id": "00123456",
        "requested_fields": ["cash_amount"],
    })
    assert result["table"] == {"columns": ["Cash Amount"], "rows": [{"cells": ["100.00"]}]}


def test_projection_does_not_change_filter_matching():
    result = mock_result(case(), AS, {
        "event_id": "unmatched", "requested_fields": ["cash_amount"],
    })
    assert result["status"] == "NO_DATA"
    assert result["table"] == {"columns": ["Cash Amount"], "rows": []}


@pytest.mark.parametrize("name", [CURRENT, EOD, SI])
def test_tm_tool_schema_and_defaults_are_unchanged(name):
    assert tool_spec(name) == historical_tool_spec(name)
    result = mock_result(case(name), name, {"account_id": "00123456"})
    assert result["status"] == "SUCCESS"
    assert result["table"]["columns"] == [FIELD_INFO[name][field]["label"] for field in DEFAULT_FIELDS[name]]


def test_as_complete_plan_deduplicates_explicit_decisive_identity_and_units():
    fields = plan_fields(AS,
        explicit=["cash_amount", "tax_amount", "timestamp"],
        decisive=["payment_status", "payment_date", "cash_amount"],
        identity=["event_id", "account_id", "isin"], qualifiers=["currency"])
    assert fields == ["cash_amount", "tax_amount", "timestamp", "payment_status", "payment_date",
                      "event_id", "account_id", "isin", "currency"]


@pytest.mark.parametrize("fields", [[], ["mt564_timestamp"], ["settlement_currency_code"], ["*"]])
def test_as_plan_does_not_invent_fields_or_empty_evidence(fields):
    with pytest.raises(ValueError):
        plan_fields(AS, explicit=fields)


def test_all_available_as_outputs_uses_exact_registry_not_wildcard():
    assert plan_fields(AS, all_outputs=True) == list(FIELD_INFO[AS])


def test_tm_adds_only_needed_outputs_not_already_in_defaults():
    assert plan_fields(CURRENT, explicit=["trade_status", "fail_text"],
                       decisive=["fail_market_status"], identity=["client_reference"]) == ["fail_text"]


@pytest.mark.parametrize("name", [AS, CURRENT, EOD, SI])
def test_more_than_six_required_columns_are_shown_in_source_order(name):
    source = source_table(name, rows=2)
    fields = list(FIELD_INFO[name])[:9]
    required = required_headers(name, explicit=fields[:4], decisive=fields[4:8], identity=fields[8:])
    shown = presentation_table(source, list(reversed(required)))
    assert len(shown["columns"]) == 9
    assert shown["columns"] == source["columns"][:9]
    assert len(shown["rows"]) == 2
    validate_presentation(source, shown, required)


def test_all_deliberately_requested_as_evidence_is_displayed():
    fields = plan_fields(AS, explicit=["cash_amount", "timestamp", "payment_date"],
                        decisive=["payment_status"], identity=["event_id", "account_id", "isin"],
                        qualifiers=["currency"])
    result = mock_result(case(), AS, {"event_id": "0001000001", "requested_fields": fields})
    shown = presentation_table(result["table"], [FIELD_INFO[AS][f]["label"] for f in fields])
    assert len(shown["columns"]) == 8
    assert shown == result["table"]


@pytest.mark.parametrize("mutation", ["drop_requested", "drop_row", "rename", "reorder", "invent_cell"])
def test_missing_asked_or_decisive_evidence_and_source_changes_fail(mutation):
    source = source_table(rows=2)
    required = source["columns"][:9]
    shown = presentation_table(source, required)
    if mutation == "drop_requested":
        shown["columns"].pop()
        for row in shown["rows"]:
            row["cells"].pop()
    elif mutation == "drop_row":
        shown["rows"].pop()
    elif mutation == "rename":
        shown["columns"][0] = "Invented header"
    elif mutation == "reorder":
        shown["columns"].reverse()
        for row in shown["rows"]:
            row["cells"].reverse()
    else:
        shown["rows"][0]["cells"][0] = "generated value"
    with pytest.raises(ValueError):
        validate_presentation(source, shown, required)


def test_unavailable_requested_header_cannot_be_synthesized():
    with pytest.raises(ValueError, match="unavailable"):
        presentation_table(source_table(), ["Key Date"])


@pytest.mark.parametrize("rows,explicit,expected", [
    (0, False, "NONE"), (0, True, "NONE"), (1, False, "COMPACT_EVIDENCE"),
    (10, False, "COMPACT_EVIDENCE"), (11, False, "SUMMARY_OFFER"),
    (50, False, "SUMMARY_OFFER"), (11, True, "FULL_TABLE"), (50, True, "FULL_TABLE"),
])
def test_row_threshold_and_explicit_override_stay_unchanged(rows, explicit, expected):
    assert evidence_mode(rows, explicit_table=explicit) == expected


def test_combined_service_threshold_is_not_per_table():
    assert evidence_mode(8 + 3) == "SUMMARY_OFFER"


def test_full_view_keeps_all_columns_rows_null_blank_and_punctuation():
    source = source_table(rows=11)
    before = deepcopy(source)
    shown = presentation_table(source, ["Event ID"], full=True, date_headers=["Payment Date"])
    expected = deepcopy(source)
    index = expected["columns"].index("Payment Date")
    for row in expected["rows"]:
        row["cells"][index] = "2026-01-01"
    assert shown == expected
    assert source == before
    validate_presentation(source, shown, ["Event ID"], full=True, date_headers=["Payment Date"])


@pytest.mark.parametrize("source_present,new_fact,headers,expected", [
    (True, False, ["Event ID"], False),
    (False, False, ["Event ID"], True),
    (True, False, ["Tax Amount"], True),
    (True, True, ["Event ID"], True),
])
def test_new_fields_or_fresh_operational_questions_need_lookup(source_present, new_fact, headers, expected):
    assert needs_lookup(complete_source=source_present, returned_headers=["Event ID", "Cash Amount"],
                        requested_headers=headers, new_fact=new_fact) == expected


@pytest.mark.parametrize("number", [4, 5])
def test_input_filter_and_date_sections_are_byte_for_byte_unchanged(number):
    assert section(PROMPT["instruction"], number) == section(BASELINE["instruction"], number)


def test_ui_schema_and_runtime_keys_are_unchanged():
    for key in ("output_schema", "response_type", "output_key"):
        assert PROMPT[key] == BASELINE[key]
    Draft202012Validator.check_schema(json.loads(PROMPT["output_schema"]))


def test_new_prompt_policies_have_no_previous_column_cap_or_as_default_assumption():
    instruction = PROMPT["instruction"]
    assert "AS_OUTPUT_SELECTION" in instruction
    assert "Every AS data call must include a non-empty requested_fields" in instruction
    assert "An input filter does not automatically return its corresponding column" in instruction
    assert "TM retains its registered mandatory defaults" in instruction
    assert "COLUMN_COVERAGE" in instruction
    assert "Each approved business tool may be called at most once per turn" in instruction
    assert "dispatch independent calls together in one model action" in instruction
    assert "no numeric display-column cap" in instruction
    assert "No sequential reference fallback, retry, extra-field lookup, or second-page call" in instruction
    assert not re.search(r"six.column|at most six|up to 6 columns|both (?:display )?caps", instruction, re.I)
