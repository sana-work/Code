#!/usr/bin/env python3
"""Synthetic-only prompt harness: no database or banking service connections."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

import yaml
from jsonschema import Draft202012Validator
from fixtures import AS, CURRENT, EOD, SI, CASES, DEFAULT_FIELDS, FIELD_INFO

ORDER = [AS, CURRENT, EOD, SI]
ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPT = ROOT.parent / "Universal_Chat_Single_Agent_System_Prompt.yaml"
DEFAULT_RUN = ROOT / "reports" / "live"
DEFAULT_SNAPSHOT = ROOT / "reports" / "prompt_snapshot.yaml"
OFFER = "Would you like me to show the supporting details in a table?"
REQUIRED = {"status", "intent", "answer", "attributes", "tables", "options", "toolsUsed"}
FILTERS = {
    AS: ["event_id", "account_id", "isin", "event_type", "event_category",
         "payment_date", "record_date", "payment_status"],
    CURRENT: ["executed_trade_id", "client_reference", "custodian_reference",
              "account_id", "isin", "cusip", "sedol", "trade_date",
              "contractual_settlement_date", "actual_settlement_date", "trade_status",
              "status", "counterparty", "place_of_settlement"],
    EOD: ["client_reference", "custodian_reference", "deal_reference", "miti_reference",
          "matching_reference", "market_reference", "account_id", "isin", "cusip",
          "sedol", "contractual_settlement_date", "actual_settlement_date",
          "close_of_business_date", "trade_status", "counterparty"],
    SI: ["client_reference", "custodian_reference", "account_id", "isin",
         "cash_account_id", "trade_date", "actual_settlement_date", "status",
         "counterparty", "settlement_location", "how_position_is_held"],
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def get_case(case_id):
    matches = [c for c in CASES if c["id"] == case_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown or duplicate case: {case_id}")
    return deepcopy(matches[0])


def load_prompt(path):
    raw = Path(path).read_text(encoding="utf-8")
    config = yaml.safe_load(raw)
    schema = json.loads(config["output_schema"])
    Draft202012Validator.check_schema(schema)
    if config["response_type"] != "JSON" or config["output_key"] != "schema":
        raise ValueError("Unexpected runtime configuration")
    return config, schema, hashlib.sha256(raw.encode()).hexdigest()


def trace_path(run_dir, case_id):
    return Path(run_dir) / f"{case_id}.trace.json"


def load_trace(run_dir, case_id):
    path = trace_path(run_dir, case_id)
    return read_json(path) if path.exists() else {"case_id": case_id, "events": []}


def tool_spec(name):
    fields = FIELD_INFO[name]
    properties = {}
    for field in FILTERS[name]:
        description = fields.get(field, {}).get("description", f"Exact {field} business filter.")
        properties[field] = {"type": "string", "description": description}
    if name == AS:
        properties["account_id"]["pattern"] = "^[0-9]+$"
    properties.update({
        "requested_fields": {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": list(fields)},
            "description": "Add these registered output fields to the mandatory defaults.",
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        "offset": {"type": "integer", "minimum": 0},
    })
    columns = "; ".join(
        f"{field} => {info['label']}: {info['description']}"
        for field, info in fields.items()
    )
    scope = {
        AS: "Asset Services corporate-action event and payment facts.",
        CURRENT: "Current transaction facts. trade_date is execution date; settlement filter is contractual_settlement_date.",
        EOD: "End-of-day snapshots. Preserve close_of_business_date. Settlement filter is contractual_settlement_date.",
        SI: "Settlement instructions. trade_date is the settlement-date equivalent. No price, currency, trade_status or fail_market_status.",
    }[name]
    return {
        "type": "function", "name": name, "strict": False,
        "description": (
            f"SYNTHETIC TEST TOOL. {scope} "
            "Requires a supported exact identifier/reference, or security + account/date. "
            "No data mutations. Default previous seven-day date window when no exact date is given. "
            f"Mandatory returned fields: {', '.join(DEFAULT_FIELDS[name])}. "
            "Result status is SUCCESS, NO_DATA, NEEDS_CLARIFICATION, or ERROR. "
            "SUCCESS contains table.columns and table.rows with string cells in source order. "
            "Unknown/missing display values use the literal string null, never an invented zero. "
            "No schema-defined relationship between the four services. "
            f"Registered output definitions: {columns}"
        ),
        "parameters": {"type": "object", "properties": properties, "additionalProperties": False},
    }


def public_context(case, prompt_path):
    config, schema, digest = load_prompt(prompt_path)
    return {
        "protocol": "Invoke mock tools through the dispatcher. Apply the tested prompt, not grader expectations.",
        "case_id": case["id"], "system_instruction": config["instruction"],
        "output_schema": schema, "prompt_sha256": digest,
        "tools": [tool_spec(n) for n in ORDER if n in case.get("available_tools", ORDER)],
        "history": case.get("history", []),
        "cached_tool_results": case.get("cached_results", {}),
        "current_message": {"context": case["user"], "userIsoTimestamp": case.get("timestamp")},
    }


def error_result(code, message):
    return {"status": "ERROR", "errors": [{"code": code, "message": message, "retryable": False}]}


def valid_table(table):
    return (
        isinstance(table, dict) and isinstance(table.get("columns"), list)
        and bool(table["columns"]) and all(isinstance(c, str) for c in table["columns"])
        and isinstance(table.get("rows"), list)
        and all(isinstance(r, dict) and isinstance(r.get("cells"), list)
                and len(r["cells"]) == len(table["columns"])
                and all(isinstance(v, str) for v in r["cells"])
                for r in table["rows"])
    )


def mock_result(case, name, arguments):
    if name not in case.get("available_tools", ORDER):
        return error_result("TOOLS_UNAVAILABLE", "The requested lookup is unavailable.")
    if not isinstance(arguments, dict):
        return error_result("INVALID_ARGUMENTS", "Arguments must be an object.")
    errors = list(Draft202012Validator(tool_spec(name)["parameters"]).iter_errors(arguments))
    if errors:
        return error_result("INVALID_ARGUMENTS", "A supplied argument is unsupported or invalid.")
    if name not in case["fixtures"]:
        return {"status": "NO_DATA", "table": {"columns": [], "rows": []}}
    primary = {"event_id", "account_id", "isin"} if name == AS else {
        "executed_trade_id", "client_reference", "custodian_reference", "deal_reference",
        "miti_reference", "matching_reference", "market_reference", "account_id", "isin", "cusip", "sedol"
    }
    if not any(arguments.get(k) for k in primary):
        return {"status": "NEEDS_CLARIFICATION", "errors": [
            {"code": "MISSING_BUSINESS_IDENTIFIER", "message": "Which business identifier should be used?"}
        ]}
    result = deepcopy(case["fixtures"][name])
    if result.get("status") != "SUCCESS" or not valid_table(result.get("table")):
        return result
    table = result["table"]
    label_to_field = {v["label"]: k for k, v in FIELD_INFO[name].items()}
    selected_rows = []
    for row in table["rows"]:
        values = {label_to_field.get(label, label): row["cells"][i]
                  for i, label in enumerate(table["columns"])}
        matches = True
        for key, value in arguments.items():
            if key in {"limit", "offset", "requested_fields"} or key not in values:
                continue
            source_value = values[key]
            if key.endswith("_date") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                source_value = source_value[:10]
            if source_value != value:
                matches = False
                break
        if matches:
            selected_rows.append(row)
    offset, limit = arguments.get("offset", 0), arguments.get("limit", 50)
    total = len(selected_rows)
    page = selected_rows[offset:offset + limit]
    result["pagination"] = {
        "page_number": str(offset // limit + 1),
        "total_page_count": str((total + limit - 1) // limit),
        "total_record_count": str(total),
    }
    if not page:
        result["status"] = "NO_DATA"
        result["table"] = {"columns": table["columns"], "rows": []}
        return result
    allowed = set(DEFAULT_FIELDS[name]) | set(arguments.get("requested_fields", []))
    indices = [i for i, label in enumerate(table["columns"])
               if label_to_field.get(label, label) in allowed]
    result["table"] = {
        "columns": [table["columns"][i] for i in indices],
        "rows": [{"cells": [row["cells"][i] for i in indices]} for row in page],
    }
    return result


def dispatch(case, calls, run_dir):
    if not isinstance(calls, list):
        raise ValueError("Request file must be an array of name/arguments calls")
    trace = load_trace(run_dir, case["id"])
    previous = [call["name"] for e in trace["events"] if e["type"] == "batch" for call in e["calls"]]
    seen, work = set(previous), []
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
            raise ValueError("Each request needs exactly name and arguments")
        name = call["name"]
        if name in seen:
            work.append((call, error_result("REPEATED_TOOL_CALL", "This tool was already called this turn.")))
        elif name not in ORDER:
            work.append((call, error_result("UNAPPROVED_TOOL", "The requested tool is not approved.")))
        else:
            work.append((call, None))
        seen.add(name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending = [pool.submit(mock_result, case, call["name"], call["arguments"])
                   if fixed is None else None for call, fixed in work]
        results = [{"name": call["name"], "result": fixed if fixed is not None else future.result()}
                   for (call, fixed), future in zip(work, pending)]
    trace["events"].append({"type": "batch", "calls": calls, "results": results})
    write_json(trace_path(run_dir, case["id"]), trace)
    return results


def submit(case_id, answer_path, run_dir):
    trace = load_trace(run_dir, case_id)
    trace["events"].append({"type": "final", "text": Path(answer_path).read_text(encoding="utf-8")})
    write_json(trace_path(run_dir, case_id), trace)


def evidence_tables(case, trace):
    result_map = dict(case.get("cached_results", {}))
    for event in trace["events"]:
        if event["type"] == "batch":
            result_map.update({r["name"]: r["result"] for r in event["results"]})
    return [(name, result["table"]) for name in ORDER
            if (result := result_map.get(name, {})).get("status") == "SUCCESS"
            and valid_table(result.get("table")) and result["table"]["rows"]]


def grade(case, trace, schema):
    failures, checks = [], []

    def check(name, condition, detail):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            failures.append({"rule": name, "detail": detail})

    finals = [e["text"] for e in trace["events"] if e["type"] == "final"]
    check("single_final", len(finals) == 1, f"Expected one final object; got {len(finals)}")
    check("no_preliminary_response", not any(e["type"] == "preliminary_response" for e in trace["events"]),
          "The model emitted a preliminary answer before the final payload")
    if len(finals) != 1:
        return {"case_id": case["id"], "status": "FAIL", "failures": failures, "checks": checks}
    try:
        response = json.loads(finals[0])
    except (json.JSONDecodeError, TypeError):
        check("valid_json", False, "Final response is not exactly one plain JSON object")
        return {"case_id": case["id"], "status": "FAIL", "failures": failures, "checks": checks}
    schema_errors = list(Draft202012Validator(schema).iter_errors(response))
    check("ui_schema", not schema_errors, "; ".join(str(e.message) for e in schema_errors))
    if not isinstance(response, dict) or schema_errors:
        return {"case_id": case["id"], "status": "FAIL", "failures": failures, "checks": checks}
    expected = case["expected"]
    allowed_keys = REQUIRED | ({"error"} if response["status"] == "FAILED" else set())
    check("exact_ui_fields", set(response) == allowed_keys, "Extra/missing top-level properties")
    check("outcome", response["status"] == expected["status"],
          f"Expected {expected['status']}, got {response['status']}")
    if response["status"] == "FAILED":
        check("safe_error", bool(response.get("error")), "FAILED requires a nonempty error")
    if "error" in expected:
        check("error_code", response.get("error") == expected["error"], "Wrong safe error")
    batches = [e for e in trace["events"] if e["type"] == "batch"]
    calls = [c for b in batches for c in b["calls"]]
    names = [c["name"] for c in calls]
    check("tool_selection", names == expected["tools"], f"Expected {expected['tools']}, got {names}")
    check("once_per_tool", len(names) == len(set(names)), "A tool was called twice")
    check("one_parallel_batch", len(batches) <= 1, "Sequential or fallback calls detected")
    check("tools_used", response["toolsUsed"] == list(dict.fromkeys(names)), "toolsUsed differs from actual calls")
    for call in calls:
        name, arguments = call["name"], call["arguments"]
        legal = name in ORDER and isinstance(arguments, dict)
        if legal:
            legal = not list(Draft202012Validator(tool_spec(name)["parameters"]).iter_errors(arguments))
        check(f"registered_arguments:{name}", legal, "Invalid/unsupported tool arguments")
        if not isinstance(arguments, dict):
            continue
        supplied_context = case["user"] + "\n" + "\n".join(
            item["content"] for item in case.get("history", []) if item["role"] == "user")
        identity_fields = {"event_id", "account_id", "isin", "executed_trade_id",
                           "client_reference", "custodian_reference", "deal_reference",
                           "miti_reference", "matching_reference", "market_reference",
                           "cusip", "sedol", "cash_account_id"}
        for field in identity_fields & set(arguments):
            check(f"supplied_identifier:{name}:{field}", arguments[field] in supplied_context,
                  "An identifier absent from this case's user context was supplied")
        identifier_patterns = ({
            "event_id": r"\bevent(?:\s+id)?\s+(\d+)",
            "account_id": r"\baccount(?:\s+id)?\s+([0-9_]+)",
            "isin": r"\bISIN\s+(SYNTH\w+)",
        } if name == AS else {
            "client_reference": r"\bclient\s+reference\s+(SYN-[A-Z0-9-]+)",
        })
        for field, pattern in identifier_patterns.items():
            explicit = set(re.findall(pattern, supplied_context, re.I))
            if len(explicit) == 1:
                value = next(iter(explicit))
                check(f"preserved_scope:{name}:{field}", arguments.get(field) == value,
                      "An explicit business identifier was omitted or substituted")
        returned = [r["result"] for b in batches for r in b["results"] if r["name"] == name]
        fixture = case["fixtures"].get(name)
        if fixture is not None and returned:
            check(f"lookup_outcome:{name}", returned[-1].get("status") == fixture.get("status"),
                  "Tool arguments changed the known synthetic lookup outcome")
        for key, value in expected.get("argument_values", {}).get(name, {}).items():
            check(f"argument:{name}:{key}", arguments.get(key) == value,
                  f"Expected exact {key}={value!r}, got {arguments.get(key)!r}")
        for key in expected.get("forbidden_arguments", {}).get(name, []):
            check(f"forbidden_argument:{name}:{key}", key not in arguments,
                  "A prohibited substitute/date-range filter was supplied")
        available = set(arguments.get("requested_fields", [])) | set(DEFAULT_FIELDS.get(name, []))
        for field in expected.get("required_fields", {}).get(name, []):
            check(f"requested_field:{name}:{field}", field in available, f"Missing decisive field {field}")
    answer = response["answer"]
    check("summary", "**Summary:**" in answer, "Missing supported summary label")
    check("no_retrieval_banner", not re.search(
        r"\b(?:one|\d+)\s+(?:matching\s+)?(?:records?|rows?|snapshot records?)\s+(?:were\s+|was\s+)?(?:found|fetched|returned)"
        r"|Showing\s+\d+\s+matching\s+record", answer, re.I), "Client reply exposes lookup counts")
    check("no_internal_details", not re.search(
        r"query_as_|query_tm_|requested_fields|set_model_response|finish_task|X-Correlation-ID|clientSecret",
        answer), "Internal function/transport information in answer")
    check("no_table_position_wording", not re.search(
        r"\b(?:is|are)\s+(?:shown|provided|listed|displayed)\s+(?:above|below)\b|\bTable\s+\d+\b",
        answer, re.I), "The reply refers to a table by position or number")
    check("no_executable_markup", not re.search(r"<(?:script|iframe|style|img|svg)\b", answer, re.I),
          "Executable/presentation markup in prose")
    for value in expected.get("answer_contains", []):
        check(f"fact:{value}", value in answer, f"Missing decisive text {value!r}")
    for pattern in expected.get("answer_patterns", []):
        check(f"answer_pattern:{pattern}", bool(re.search(pattern, answer, re.I | re.S)),
              f"Missing grounded response matching {pattern}")
    for pattern in expected.get("answer_forbidden", []):
        check(f"forbidden:{pattern}", not re.search(pattern, answer, re.I | re.S),
              f"Unsupported statement matching {pattern}")
    if expected.get("email"):
        check("email_greeting", bool(re.search(r"^(?:Hello,|Dear [^\n]+,)$", answer, re.M)),
              "Email enquiry lacks reply greeting")
        check("email_closing", "Kind regards," in answer, "Email enquiry lacks closing")
    check("table_offer", (OFFER in answer) == expected.get("offer", False), "Wrong table-offer behavior")
    check("one_question", answer.count("?") <= 1, "More than one question in client reply")
    if expected.get("expect_clarification"):
        check("business_clarification", answer.count("?") == 1 and OFFER not in answer,
              "Missing the single required business clarification")
    if expected.get("offer"):
        check("presentation_status", response["status"] == "SUCCESS" and response["options"] == [],
              "A table offer is not a business clarification")
    source, tables = evidence_tables(case, trace), response["tables"]
    count = 0 if expected["display"] == "none" else len(source)
    check("table_presence", len(tables) == count, f"Expected {count} evidence tables, got {len(tables)}")
    placeholders = re.findall(r"<<(table_\d+)>>", answer)
    check("table_placeholders", placeholders == [t["id"] for t in tables], "Wrong table/placeholder pairing")
    check("table_ids", [t["id"] for t in tables] == [f"table_{i+1}" for i in range(len(tables))],
          "Nonsequential table IDs")
    if tables:
        check("appendix_last", answer.rstrip().endswith(f"<<{tables[-1]['id']}>>"),
              "Narrative/question/closing follows the evidence appendix")
        first = answer.find(f"<<{tables[0]['id']}>>")
        check("summary_first", answer.find("**Summary:**") < first, "Table precedes summary")
        if expected.get("email"):
            check("closing_before_table", answer.find("Kind regards,") < first, "Closing follows table")
        for table in tables:
            token = re.escape(f"<<{table['id']}>>")
            check(f"title:{table['id']}", bool(re.search(r"\*\*[^\n*]+\*\*\s*\n\s*\n" + token, answer)),
                  "Evidence table lacks a separate bold title")
    for table, (tool, original) in zip(tables, source):
        check(f"table_shape:{tool}", set(table) == {"id", "columns", "rows"} and valid_table(table),
              "Invalid table structure")
        if not valid_table(table):
            continue
        if expected["display"] == "full":
            check(f"full_columns:{tool}", table["columns"] == original["columns"], "Full columns altered/omitted")
            check(f"full_rows:{tool}", table["rows"] == original["rows"], "Full rows/cells altered/omitted")
        else:
            check(f"compact_width:{tool}", 1 <= len(table["columns"]) <= 6, "Compact table exceeds six columns")
            indices, start = [], 0
            for label in table["columns"]:
                try:
                    index = original["columns"].index(label, start)
                except ValueError:
                    index = -1
                if index >= 0:
                    indices.append(index)
                    start = index + 1
            check(f"source_headers:{tool}", len(indices) == len(table["columns"]), "Invented/reordered headers")
            projected = [{"cells": [r["cells"][i] for i in indices]} for r in original["rows"]]
            check(f"source_cells:{tool}", table["rows"] == projected, "Cells/rows differ from source projection")
    if any(tool != AS for tool, _ in source):
        for label in ("**Parties involved**:", "**Settlement information**:", "**Current Status & Action Required**:"):
            check(f"tm_label:{label}", label in answer, "Missing TM detail label")
    return {"case_id": case["id"], "status": "FAIL" if failures else "PASS",
            "failures": failures, "checks": checks}


def make_report(run_dir, prompt_path, out):
    _, schema, digest = load_prompt(prompt_path)
    rows = []
    for case in CASES:
        path = trace_path(run_dir, case["id"])
        if path.exists():
            rows.append(grade(case, read_json(path), schema))
        else:
            rows.append({"case_id": case["id"], "status": "NOT_RUN", "failures": [], "checks": []})
    counts = {k: sum(r["status"] == k for r in rows) for k in ("PASS", "FAIL", "NOT_RUN")}
    report = {
        "suite": "Universal Chat synthetic prompt evaluation", "synthetic_only": True,
        "prompt_sha256": digest, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "Codex agents with a local mock-tool adapter, or direct Responses API",
        "coverage": counts, "cases": rows,
        "limitations": [
            "Synthetic schemas are not the deployed banking tool schemas.",
            "Checks cover structure, table fidelity, call traces and selected factual assertions.",
            "Semantic quality, unseen inputs, UI rendering and the deployed model require further evaluation.",
            "NOT_RUN cases are never counted as passed.",
        ],
    }
    out = Path(out)
    write_json(out, report)
    lines = ["# Synthetic Prompt Test Report", "", f"Prompt SHA256: {digest}", "",
             f"**{counts['PASS']} passed; {counts['FAIL']} failed; {counts['NOT_RUN']} not run.**", "",
             "All data is fabricated. Live Codex-agent outputs use a mock-tool adapter; "
             "this is not a run against the deployed Citi model or services.", "",
             "| Case | Result | Findings |", "| --- | --- | --- |"]
    for row in rows:
        findings = "; ".join(f"{f['rule']}: {f['detail']}" for f in row["failures"]) or ""
        lines.append(f"| {row['case_id']} | {row['status']} | {findings.replace('|', '/')} |")
    lines += ["", "## Limits", ""] + [f"- {x}" for x in report["limitations"]]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def run_api(case, prompt_path, run_dir, model, base_url):
    key = os.getenv("OPENAI_API_KEY")
    if not key or not model:
        raise ValueError("Direct model mode needs OPENAI_API_KEY and --model or OPENAI_MODEL")
    public = public_context(case, prompt_path)
    instructions = public["system_instruction"] + "\n\nOUTPUT_SCHEMA:\n" + json.dumps(public["output_schema"])
    history = list(public["history"])
    if public["cached_tool_results"]:
        history.append({"role": "developer", "content": "Previously returned complete synthetic tool results:\n"
                        + json.dumps(public["cached_tool_results"])})
    history.append({"role": "user", "content": json.dumps(public["current_message"])})
    request_input = history
    url = base_url.rstrip("/") + "/responses"
    for _ in range(4):
        body = {
            "model": model, "instructions": instructions, "input": request_input,
            "tools": public["tools"], "parallel_tool_calls": True,
            "text": {"format": {"type": "json_object"}}, "store": False,
            "max_output_tokens": 16000,
        }
        request = urllib.request.Request(url, json.dumps(body).encode(),
                                         {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Model endpoint returned HTTP {exc.code}; credentials are not logged") from None
        outputs = payload.get("output", [])
        functions = [o for o in outputs if o.get("type") == "function_call"]
        messages = [c.get("text", "") for o in outputs if o.get("type") == "message"
                    for c in o.get("content", []) if c.get("type") == "output_text"]
        if functions:
            if messages and any(x.strip() for x in messages):
                trace = load_trace(run_dir, case["id"])
                trace["events"].append({"type": "preliminary_response", "text": "".join(messages)})
                write_json(trace_path(run_dir, case["id"]), trace)
            calls = [{"name": f["name"], "arguments": json.loads(f["arguments"])} for f in functions]
            results = dispatch(case, calls, run_dir)
            request_input.extend(outputs)
            request_input.extend({"type": "function_call_output", "call_id": f["call_id"],
                                  "output": json.dumps(r["result"])}
                                 for f, r in zip(functions, results))
        else:
            trace = load_trace(run_dir, case["id"])
            trace["events"].append({"type": "final", "text": "".join(messages)})
            write_json(trace_path(run_dir, case["id"]), trace)
            return
    raise RuntimeError("Agent exceeded the limited tool/final-response cycle")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=str(DEFAULT_SNAPSHOT if DEFAULT_SNAPSHOT.exists() else DEFAULT_PROMPT))
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN))
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("list")
    init = subs.add_parser("init")
    init.add_argument("--out", default=str(DEFAULT_SNAPSHOT))
    ctx = subs.add_parser("context")
    ctx.add_argument("--case", required=True)
    ctx.add_argument("--brief", action="store_true")
    dp = subs.add_parser("dispatch")
    dp.add_argument("--case", required=True)
    dp.add_argument("--request-file", required=True)
    sp = subs.add_parser("submit")
    sp.add_argument("--case", required=True)
    sp.add_argument("--response-file", required=True)
    gp = subs.add_parser("grade")
    gp.add_argument("--case")
    gp.add_argument("--out", default=str(ROOT / "reports" / "evaluation.json"))
    api = subs.add_parser("run-api")
    api.add_argument("--case", action="append")
    api.add_argument("--model", default=os.getenv("OPENAI_MODEL"))
    api.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    args = parser.parse_args()
    if args.command == "list":
        print(json.dumps([{"id": c["id"], "question": c["user"]} for c in CASES], indent=2))
    elif args.command == "init":
        load_prompt(args.prompt)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(Path(args.prompt).read_text(encoding="utf-8"), encoding="utf-8")
        print(json.dumps({"snapshot": str(path)}))
    elif args.command == "context":
        context = public_context(get_case(args.case), args.prompt)
        if args.brief:
            context["available_tools"] = [tool["name"] for tool in context.pop("tools")]
            context.pop("system_instruction")
            context.pop("output_schema")
        print(json.dumps(context, indent=2, ensure_ascii=True))
    elif args.command == "dispatch":
        print(json.dumps(dispatch(get_case(args.case), read_json(args.request_file), args.run_dir),
                         indent=2, ensure_ascii=True))
    elif args.command == "submit":
        get_case(args.case)
        submit(args.case, args.response_file, args.run_dir)
        print(json.dumps({"submitted": args.case}))
    elif args.command == "grade":
        if args.case:
            _, schema, _ = load_prompt(args.prompt)
            print(json.dumps(grade(get_case(args.case), load_trace(args.run_dir, args.case), schema), indent=2))
        else:
            report = make_report(args.run_dir, args.prompt, args.out)
            print(json.dumps({"coverage": report["coverage"], "report": args.out}))
    else:
        selected = [get_case(c) for c in args.case] if args.case else CASES
        for case in selected:
            if trace_path(args.run_dir, case["id"]).exists():
                raise ValueError("Use a fresh run directory to preserve prior observations")
            run_api(case, args.prompt, args.run_dir, args.model, args.base_url)
            print(json.dumps({"completed": case["id"]}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"Test harness error: {exc}", file=sys.stderr)
        sys.exit(2)
