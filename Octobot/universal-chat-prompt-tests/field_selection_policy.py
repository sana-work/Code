"""Synthetic reference policy for the 27 October output-selection contract.

This is not a model, production tool adapter, or natural-language planner.
It checks explicit field plans and exact table projections using the historical
invented registry. The original dispatcher, observations, and scores stay frozen.
"""
from copy import deepcopy

from jsonschema import Draft202012Validator

from fixtures import AS, DEFAULT_FIELDS, FIELD_INFO
from harness import mock_result as historical_mock_result
from harness import tool_spec as historical_tool_spec
from harness import valid_table
from test_zero_time_date_display import display_date


def tool_spec(name):
    spec = deepcopy(historical_tool_spec(name))
    if name == AS:
        fields = spec["parameters"]["properties"]["requested_fields"]
        fields["minItems"] = 1
        fields["description"] = "Explicit AS output projection. No output defaults."
        spec["parameters"]["required"] = ["requested_fields"]
        old = f"Mandatory returned fields: {', '.join(DEFAULT_FIELDS[AS])}. "
        spec["description"] = spec["description"].replace(
            old, "No default output columns; requested_fields is required and non-empty. "
        )
    return spec


def plan_fields(name, *, explicit=(), decisive=(), identity=(), qualifiers=(), all_outputs=False):
    """Deduplicate already-resolved fields; do not infer business mappings."""
    registry = FIELD_INFO[name]
    union = list(dict.fromkeys([*explicit, *decisive, *identity, *qualifiers]))
    if any(field not in registry for field in union):
        raise ValueError("Unregistered output field")
    if all_outputs:
        union = list(registry)
    if name == AS:
        if not union:
            raise ValueError("AS needs an explicit evidence set")
        return union
    return [field for field in union if field not in DEFAULT_FIELDS[name]]


def mock_result(case, name, arguments):
    errors = list(Draft202012Validator(tool_spec(name)["parameters"]).iter_errors(arguments))
    if errors:
        return {"status": "ERROR", "errors": [{"code": "INVALID_ARGUMENTS"}]}
    result = historical_mock_result(case, name, arguments)
    if name != AS or result.get("status") not in {"SUCCESS", "NO_DATA"} or not valid_table(result.get("table")):
        return result
    requested = {FIELD_INFO[AS][field]["label"] for field in arguments["requested_fields"]}
    table = result["table"]
    indices = [i for i, column in enumerate(table["columns"]) if column in requested]
    result["table"] = {
        "columns": [table["columns"][i] for i in indices],
        "rows": [{"cells": [row["cells"][i] for i in indices]} for row in table["rows"]],
    }
    return result


def required_headers(name, **field_groups):
    requested = plan_fields(name, **field_groups)
    # TM plan_fields returns additions only; display coverage still includes
    # explicit/decisive fields already covered by TM defaults.
    if name != AS:
        requested = list(dict.fromkeys([
            *field_groups.get("explicit", ()), *field_groups.get("decisive", ()),
            *field_groups.get("identity", ()), *field_groups.get("qualifiers", ()),
        ]))
        if field_groups.get("all_outputs"):
            requested = list(FIELD_INFO[name])
    return [FIELD_INFO[name][field]["label"] for field in requested]


def evidence_mode(row_count, *, explicit_table=False):
    if row_count == 0:
        return "NONE"
    if explicit_table:
        return "FULL_TABLE"
    return "COMPACT_EVIDENCE" if row_count <= 10 else "SUMMARY_OFFER"


def presentation_table(source, required, *, full=False, date_headers=()):
    if not valid_table(source):
        raise ValueError("INVALID_TOOL_RESULT")
    if not set(required).issubset(source["columns"]):
        raise ValueError("Requested evidence unavailable")
    indices = [i for i, column in enumerate(source["columns"]) if full or column in required]
    if not indices:
        raise ValueError("No evidence columns selected")
    return {
        "columns": [source["columns"][i] for i in indices],
        "rows": [{"cells": [
            display_date(row["cells"][i], registered_date_field=source["columns"][i] in date_headers)
            for i in indices
        ]} for row in source["rows"]],
    }


def validate_presentation(source, displayed, required, *, full=False, date_headers=()):
    expected = presentation_table(source, required, full=full, date_headers=date_headers)
    if displayed != expected:
        raise ValueError("Evidence coverage, order, or value mismatch")


def needs_lookup(*, complete_source, returned_headers, requested_headers=(), new_fact=False):
    return new_fact or not complete_source or not set(requested_headers).issubset(returned_headers)
