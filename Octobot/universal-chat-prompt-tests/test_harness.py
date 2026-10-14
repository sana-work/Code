from copy import deepcopy
import io
import json
from pathlib import Path

import pytest

import harness as h
from fixtures import AS, CURRENT


def setup_response(case_id="as_cash_paid", full=False):
    case = h.get_case(case_id)
    args = {"event_id": "0001000001", "account_id": "00123456", "limit": 50, "offset": 0}
    if "full_table" in case_id:
        args = {"account_id": "00123456", "limit": 50, "offset": 0}
    result = h.mock_result(case, AS, args)
    source = result["table"]
    if full:
        table = {"id": "table_1", **deepcopy(source)}
        answer = "**Summary:** The supporting details are provided.\n\n**Supporting event details**\n\n<<table_1>>"
    else:
        indices = [0, 1, 5, 6, 8, 9]
        table = {"id": "table_1", "columns": [source["columns"][i] for i in indices],
                 "rows": [{"cells": [r["cells"][i] for i in indices]} for r in source["rows"]]}
        answer = "**Summary:** Cash of **100.00 CAD** was paid.\n\n**Supporting payment details**\n\n<<table_1>>"
    response = {"status": "SUCCESS", "intent": "Answer the client enquiry.", "answer": answer,
                "attributes": [], "tables": [table], "options": [], "toolsUsed": [AS]}
    trace = {"case_id": case["id"], "events": [
        {"type": "batch", "calls": [{"name": AS, "arguments": args}],
         "results": [{"name": AS, "result": result}]},
        {"type": "final", "text": json.dumps(response)},
    ]}
    return case, trace, response


def grade(case, trace):
    _, schema, _ = h.load_prompt(h.DEFAULT_SNAPSHOT)
    return h.grade(case, trace, schema)


def update_final(trace, response):
    trace["events"][-1]["text"] = json.dumps(response)


def test_compact_control_is_valid():
    case, trace, _ = setup_response()
    report = grade(case, trace)
    assert report["status"] == "PASS", report["failures"]


def test_full_control_is_valid():
    case, trace, _ = setup_response("as_full_table_preserves_special_cells_scoped", True)
    report = grade(case, trace)
    assert report["status"] == "PASS", report["failures"]


@pytest.mark.parametrize("mutation", ["drop_column", "drop_row", "change_comma",
                                     "blank_cell", "rename_header", "reverse_rows"])
def test_full_table_mutations_are_detected(mutation):
    case, trace, response = setup_response("as_full_table_preserves_special_cells_scoped", True)
    table = response["tables"][0]
    if mutation == "drop_column":
        table["columns"].pop()
        for row in table["rows"]:
            row["cells"].pop()
    elif mutation == "drop_row":
        table["rows"].pop()
    elif mutation == "change_comma":
        table["rows"][0]["cells"][10] = "Trailing commas"
    elif mutation == "blank_cell":
        table["rows"][0]["cells"][0] = ""
    elif mutation == "rename_header":
        table["columns"][0] = "Invented Header"
    else:
        table["rows"].reverse()
    update_final(trace, response)
    report = grade(case, trace)
    assert report["status"] == "FAIL"
    assert any(f["rule"].startswith("full_") for f in report["failures"])


def test_duplicate_final_detected():
    case, trace, _ = setup_response()
    trace["events"].append(deepcopy(trace["events"][-1]))
    assert any(f["rule"] == "single_final" for f in grade(case, trace)["failures"])


def test_two_json_objects_detected():
    case, trace, _ = setup_response()
    trace["events"][-1]["text"] += trace["events"][-1]["text"]
    assert any(f["rule"] == "valid_json" for f in grade(case, trace)["failures"])


def test_narrative_after_appendix_detected():
    case, trace, response = setup_response()
    response["answer"] += "\n\nAn extra conclusion."
    update_final(trace, response)
    assert any(f["rule"] == "appendix_last" for f in grade(case, trace)["failures"])


def test_lookup_count_banner_detected():
    case, trace, response = setup_response()
    response["answer"] = response["answer"].replace("**Summary:**", "**Summary:** 1 record was found.")
    update_final(trace, response)
    assert any(f["rule"] == "no_retrieval_banner" for f in grade(case, trace)["failures"])


@pytest.mark.parametrize("wording", ["The information is shown below.", "See Table 1."])
def test_table_position_wording_detected(wording):
    case, trace, response = setup_response()
    response["answer"] = response["answer"].replace("**Summary:**", "**Summary:** " + wording)
    update_final(trace, response)
    assert any(f["rule"] == "no_table_position_wording" for f in grade(case, trace)["failures"])


def test_optional_field_only_returned_if_requested():
    case = h.get_case("as_latest_mt566_optional_timestamp")
    no_field = h.mock_result(case, AS, {"event_id": "0001000001"})
    with_field = h.mock_result(case, AS, {"event_id": "0001000001", "requested_fields": ["timestamp"]})
    label = h.FIELD_INFO[AS]["timestamp"]["label"]
    assert label not in no_field["table"]["columns"]
    assert label in with_field["table"]["columns"]


def test_identifier_not_silently_repaired():
    case = h.get_case("as_cash_paid")
    result = h.mock_result(case, AS, {"event_id": "1000001"})
    assert result["status"] == "NO_DATA"


def test_unregistered_field_returns_error():
    case = h.get_case("as_cash_paid")
    result = h.mock_result(case, AS, {"event_id": "0001000001", "requested_fields": ["mt564_timestamp"]})
    assert result["status"] == "ERROR"


def test_repeated_tool_is_recorded_and_rejected(tmp_path):
    case = h.get_case("as_cash_paid")
    calls = [{"name": AS, "arguments": {"event_id": "0001000001"}}]
    h.dispatch(case, calls, tmp_path)
    result = h.dispatch(case, calls, tmp_path)
    assert result[0]["result"]["errors"][0]["code"] == "REPEATED_TOOL_CALL"
    assert len(h.load_trace(tmp_path, case["id"])["events"]) == 2


def test_multiple_tools_one_batch(tmp_path):
    case = h.get_case("mixed_partial_success_as_current_timeout")
    calls = [{"name": AS, "arguments": {"event_id": "0001000001"}},
             {"name": CURRENT, "arguments": {"client_reference": "SYN-CLIENT-01"}}]
    h.dispatch(case, calls, tmp_path)
    trace = h.load_trace(tmp_path, case["id"])
    assert len(trace["events"]) == 1
    assert [r["name"] for r in trace["events"][0]["results"]] == [AS, CURRENT]


def test_no_private_oracle_in_actor_context():
    public = h.public_context(h.get_case("as_cash_paid"), h.DEFAULT_SNAPSHOT)
    assert "expected" not in public
    assert "fixtures" not in public
    assert "system_instruction" in public
    assert "tools" in public


def test_case_catalogue_has_valid_expectations():
    assert len({c["id"] for c in h.CASES}) == len(h.CASES)
    for case in h.CASES:
        assert case["expected"]["status"] in {"SUCCESS", "FAILED", "NEEDS_CLARIFICATION", "OUT_OF_SCOPE"}
        assert case["expected"]["display"] in {"none", "compact", "full"}
        assert "error" not in case["expected"] or case["expected"]["status"] == "FAILED"


def test_unrun_cases_never_pass(tmp_path):
    report = h.make_report(tmp_path, h.DEFAULT_SNAPSHOT, tmp_path / "report.json")
    assert report["coverage"]["PASS"] == 0
    assert report["coverage"]["NOT_RUN"] == len(h.CASES)


def test_api_configuration_missing_is_explicit(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        h.run_api(h.get_case("as_cash_paid"), h.DEFAULT_SNAPSHOT, tmp_path, "test-model", "https://example.invalid/v1")


def test_responses_adapter_with_stub_provider(monkeypatch, tmp_path):
    case, _, final = setup_response()
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    requests = []
    replies = [
        {"output": [{"type": "function_call", "call_id": "synthetic_call_1",
                     "name": AS, "arguments": json.dumps({"event_id": "0001000001",
                                                         "account_id": "00123456"})}]},
        {"output": [{"type": "message", "content": [{"type": "output_text",
                                                    "text": json.dumps(final)}]}]},
    ]

    def urlopen(request, timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps(replies.pop(0)).encode())

    monkeypatch.setattr(h.urllib.request, "urlopen", urlopen)
    h.run_api(case, h.DEFAULT_SNAPSHOT, tmp_path, "synthetic-model", "https://example.invalid/v1")
    assert requests[0]["parallel_tool_calls"] is True
    assert any(item.get("type") == "function_call_output" for item in requests[1]["input"])
    trace = h.load_trace(tmp_path, case["id"])
    assert grade(case, trace)["status"] == "PASS"
