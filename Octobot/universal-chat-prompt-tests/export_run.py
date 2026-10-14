#!/usr/bin/env python3
"""Package provenance and readable examples from preserved live observations."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import harness as h


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    config, _, prompt_hash = h.load_prompt(h.DEFAULT_SNAPSHOT)
    h.write_json(h.ROOT / "reports" / "case_catalogue.json", h.CASES)
    h.write_json(h.ROOT / "reports" / "registered_synthetic_tools.json",
                 [h.tool_spec(name) for name in h.ORDER])
    cases = []
    for case in h.CASES:
        path = h.trace_path(h.DEFAULT_RUN, case["id"])
        trace = h.read_json(path)
        finals = [event for event in trace["events"] if event["type"] == "final"]
        if len(finals) != 1:
            raise ValueError(f"Not one complete first-attempt observation: {case['id']}")
        context = h.public_context(case, h.DEFAULT_SNAPSHOT)
        cases.append({
            "case_id": case["id"],
            "public_context_sha256": hashlib.sha256(
                json.dumps(context, sort_keys=True).encode()).hexdigest(),
            "trace_path": str(path.relative_to(h.ROOT)),
            "trace_sha256": digest(path),
        })
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "Live Codex testing agents through local synthetic tool dispatcher",
        "production_model_run": False,
        "native_banking_tool_run": False,
        "api_model_run": False,
        "ui_renderer_tested": False,
        "actor_model_identifier": "Not captured by this local adapter",
        "prompt_sha256": prompt_hash,
        "ui_schema_sha256": hashlib.sha256(config["output_schema"].encode()).hexdigest(),
        "table_copying": "Code-assisted exact copying/projection; actor chose mode and indices",
        "oracle_isolation": "Procedural instruction; no filesystem security boundary",
        "actor_groups": [
            {"id": "01a13895-ca27-7b50-95e2-282d162a01c2", "group": "group-1"},
            {"id": "01a13895-cb17-78b3-bcbe-49706eab94c4", "group": "group-2"},
            {"id": "01a13895-cb70-73e3-a82f-f6909d4be5ee", "group": "group-3"},
        ],
        "artifacts": {name: digest(h.ROOT / name) for name in [
            "harness.py", "fixtures.py", "test_harness.py",
            "reports/prompt_snapshot.yaml", "reports/case_catalogue.json",
            "reports/registered_synthetic_tools.json", "reports/baseline_case_catalogue.json",
        ]},
        "cases": cases,
    }
    h.write_json(h.ROOT / "reports" / "run_manifest.json", manifest)
    samples = {}
    for name in ["email_auto_detect_without_explicit_reply_request",
                 "as_suppress_eleven_rows_offer_table",
                 "as_full_table_preserves_special_cells_scoped",
                 "tm_ambiguous_client_reference_three_tools",
                 "mixed_partial_success_as_current_timeout"]:
        trace = h.load_trace(h.DEFAULT_RUN, name)
        samples[name] = json.loads(next(e["text"] for e in trace["events"] if e["type"] == "final"))
    h.write_json(h.ROOT / "reports" / "client_examples.json", samples)
    report = h.make_report(h.DEFAULT_RUN, h.DEFAULT_SNAPSHOT, h.ROOT / "reports" / "evaluation.json")
    print(json.dumps({"coverage": report["coverage"], "observations": len(cases),
                      "manifest": "reports/run_manifest.json"}))


if __name__ == "__main__":
    main()
