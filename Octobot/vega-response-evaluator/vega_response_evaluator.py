#!/usr/bin/env python3
"""Hybrid evaluator for VEGA final responses.

The script reads all audit_table rows for one correlation ID, reconstructs the
question, tool results, and final response, runs deterministic checks, and can
optionally invoke a single semantic evaluator over HTTP.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


DEFAULT_TABLE = "gssp_agentic.audit_table"
DEFAULT_CODE_WEIGHT = 0.70
DEFAULT_AGENT_WEIGHT = 0.30


@dataclass
class Metric:
    name: str
    score: int | None
    weight: int
    status: str
    evidence: list[str]
    critical: bool = False


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=True, default=json_default)
        handle.write("\n")


def validate_table_name(table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table):
        raise ValueError("Audit table must use the form schema.table")
    return table


def read_audit_rows(correlation_id: str, table: str) -> list[dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "Database mode requires psycopg. Install requirements.txt in the remote environment."
        ) from exc

    required = ["VEGA_DB_HOST", "VEGA_DB_NAME", "VEGA_DB_USER", "VEGA_DB_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing database environment variables: {', '.join(missing)}")

    safe_table = validate_table_name(table)
    query = f"""
        SELECT
            id, session_id, sequence_id, invocation_id, user_id, usecase_name,
            root_agent_name, agent_name, agent_status, tool_name, tool_status,
            function_call_id, event_type, input_args, tool_response,
            agent_response, user_message, error_message, error_type,
            model_name, prompt_tokens, completion_tokens, total_tokens,
            created_at, completed_at, x_correlation_id, country, region
        FROM {safe_table}
        WHERE x_correlation_id = %s
        ORDER BY sequence_id ASC NULLS LAST, id ASC
    """

    connection = psycopg.connect(
        host=os.environ["VEGA_DB_HOST"],
        port=int(os.getenv("VEGA_DB_PORT", "1524")),
        dbname=os.environ["VEGA_DB_NAME"],
        user=os.environ["VEGA_DB_USER"],
        password=os.environ["VEGA_DB_PASSWORD"],
        sslmode=os.getenv("VEGA_DB_SSLMODE", "require"),
        connect_timeout=int(os.getenv("VEGA_DB_CONNECT_TIMEOUT", "10")),
        row_factory=dict_row,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (correlation_id,))
            return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def decode_json_layers(value: Any, max_depth: int = 5) -> Any:
    """Decode escaped JSON strings while preserving ordinary response text."""
    current = value
    for _ in range(max_depth):
        if not isinstance(current, str):
            break
        candidate = current.strip()
        if not candidate or candidate[0] not in "{[\"":
            break
        try:
            current = json.loads(candidate)
        except json.JSONDecodeError:
            break
    return current


def unwrap_content_text(value: Any) -> Any:
    current = decode_json_layers(value)
    for _ in range(5):
        if not isinstance(current, dict):
            return current
        content = current.get("content")
        if not isinstance(content, list) or not content:
            return current
        first = content[0]
        if not isinstance(first, dict) or "text" not in first:
            return current
        current = decode_json_layers(first["text"])
    return current


def first_nonempty(rows: list[dict[str, Any]], field: str) -> str | None:
    for row in rows:
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def select_final_response(rows: list[dict[str, Any]]) -> str | None:
    candidates = [
        row
        for row in rows
        if isinstance(row.get("agent_response"), str) and row["agent_response"].strip()
    ]
    if not candidates:
        return None

    final_candidates = [
        row
        for row in candidates
        if "FINAL" in str(row.get("event_type") or "").upper()
    ]
    selected = (final_candidates or candidates)[-1]["agent_response"].strip()
    unwrapped = unwrap_content_text(selected)
    if isinstance(unwrapped, str):
        return unwrapped.strip()
    if isinstance(unwrapped, dict):
        for key in ("answer", "response", "finalResponse", "final_response", "text"):
            value = unwrapped.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return json.dumps(unwrapped, ensure_ascii=True, default=json_default)


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def normalize_table(payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    table = payload.get("table")
    if not isinstance(table, dict):
        return [], []

    columns = table.get("columns") or payload.get("columnKeys") or []
    raw_rows = table.get("rows") or []
    if not isinstance(columns, list) or not isinstance(raw_rows, list):
        return [], []

    names = [str(column) for column in columns]
    records: list[dict[str, Any]] = []
    for raw_row in raw_rows:
        cells = raw_row.get("cells") if isinstance(raw_row, dict) else raw_row
        if not isinstance(cells, list):
            continue
        record = {
            names[index]: cells[index] if index < len(cells) else None
            for index in range(len(names))
        }
        records.append(record)
    return names, records


def parse_tool_results(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in rows:
        raw = row.get("tool_response")
        if raw in (None, "", "null", "NULL"):
            continue
        payload = unwrap_content_text(raw)
        if not isinstance(payload, dict):
            warnings.append(f"Could not parse tool_response for audit row {row.get('id')}")
            continue

        columns, records = normalize_table(payload)
        result = {
            "auditId": row.get("id"),
            "sequenceId": row.get("sequence_id"),
            "toolName": payload.get("toolName") or row.get("tool_name"),
            "toolStatus": payload.get("status") or row.get("tool_status"),
            "domain": payload.get("domain"),
            "inputArgs": decode_json_layers(row.get("input_args")),
            "columnKeys": payload.get("columnKeys") or [],
            "columns": columns,
            "records": records,
            "recordCount": len(records),
            "pagination": payload.get("pagination"),
            "errors": payload.get("errors") or [],
            "isError": bool(payload.get("isError")),
        }
        results.append(result)
    return results, warnings


def resolve_execution_time(rows: list[dict[str, Any]]) -> tuple[datetime | None, str]:
    db_timezone = ZoneInfo(os.getenv("VEGA_DB_TIMEZONE", "UTC"))
    business_timezone_name = os.getenv("VEGA_BUSINESS_TIMEZONE", "Asia/Kolkata")
    business_timezone = ZoneInfo(business_timezone_name)

    values: list[datetime] = []
    for row in rows:
        for field in ("completed_at", "created_at"):
            value = row.get(field)
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    continue
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    value = value.replace(tzinfo=db_timezone)
                values.append(value.astimezone(business_timezone))
    return (max(values) if values else None), business_timezone_name


def collect_source_values(tool_results: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for result in tool_results:
        for record in result["records"]:
            for value in record.values():
                if value is not None:
                    values.add(str(value).strip())
    return values


def collect_pay_dates(tool_results: list[dict[str, Any]]) -> list[date]:
    values: list[date] = []
    for result in tool_results:
        for record in result["records"]:
            for key, raw_value in record.items():
                normalized = normalize_key(key)
                if not any(token in normalized for token in ("pay_date", "payable_date", "payment_date")):
                    continue
                try:
                    values.append(date.fromisoformat(str(raw_value)[:10]))
                except (TypeError, ValueError):
                    pass
    return values


def extract_iso_dates(text: str) -> set[str]:
    return set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))


def extract_large_identifiers(text: str) -> set[str]:
    return set(re.findall(r"(?<![\d-])\d{8,}(?![\d-])", text))


def extract_record_count_claims(text: str) -> list[int]:
    patterns = (
        r"\btotal\s+of\s+(\d+)\s+[A-Za-z -]*records?\b",
        r"\b(\d+)\s+[A-Za-z -]*records?\s+(?:are|were|was)\b",
        r"\b(?:there\s+(?:are|is|were|was))\s+(\d+)\s+[A-Za-z -]*records?\b",
    )
    claims: list[int] = []
    for pattern in patterns:
        claims.extend(int(value) for value in re.findall(pattern, text, flags=re.IGNORECASE))
    return claims


def metric(
    name: str,
    score: int | None,
    weight: int,
    evidence: Iterable[str],
    *,
    critical: bool = False,
) -> Metric:
    status = "NOT_APPLICABLE" if score is None else ("PASS" if score >= 3 else "FAIL")
    return Metric(name, score, weight, status, list(evidence), critical)


def evaluate_objective(
    question: str | None,
    final_response: str | None,
    tool_results: list[dict[str, Any]],
    execution_time: datetime | None,
    business_timezone: str,
    parse_warnings: list[str],
    rules: dict[str, Any],
) -> list[Metric]:
    response = final_response or ""
    lowered = response.lower()
    metrics: list[Metric] = []

    metrics.append(
        metric(
            "final_response_present",
            4 if response else 0,
            10,
            ["A non-empty final response was found." if response else "No final response was found."],
            critical=not bool(response),
        )
    )

    if tool_results or parse_warnings:
        score = 4 if tool_results and not parse_warnings else (2 if tool_results else 0)
        evidence = [f"Parsed {len(tool_results)} tool result(s)."] + parse_warnings
        metrics.append(metric("tool_result_integrity", score, 15, evidence, critical=score == 0))
    else:
        metrics.append(metric("tool_result_integrity", None, 15, ["No tool responses were present."]))

    statuses = [str(result.get("toolStatus") or "").upper() for result in tool_results]
    has_success = any(status == "SUCCESS" for status in statuses)
    has_no_data = any(status == "NO_DATA" for status in statuses)
    has_error = any(
        status in {"ERROR", "FAILED", "FAILURE"} or result.get("isError") or result.get("errors")
        for status, result in zip(statuses, tool_results)
    )
    if statuses:
        no_data_language = bool(
            re.search(
                r"\b(?:no\s+(?:data|records?|details?)|not\s+found|no\s+[^.]{0,80}\s+were\s+found)\b",
                lowered,
            )
        )
        success_language = any(
            phrase in lowered for phrase in ("retrieved", "available", "record", "details", "result")
        )
        error_language = any(
            phrase in lowered for phrase in ("error", "failed", "unavailable", "could not retrieve")
        )
        if has_error:
            score = 4 if error_language else 0
            evidence = ["At least one tool returned an error.", f"Response disclosed error: {error_language}."]
        elif has_no_data and has_success:
            score = 4 if no_data_language and success_language else 2
            evidence = [
                "Execution contains both NO_DATA and SUCCESS outcomes.",
                f"Response acknowledged missing data: {no_data_language}.",
                f"Response retained successful data: {success_language}.",
            ]
        elif has_no_data:
            score = 4 if no_data_language else 1
            evidence = [f"Response acknowledged the NO_DATA outcome: {no_data_language}."]
        else:
            score = 4
            evidence = ["All parsed tool outcomes were successful."]
        metrics.append(metric("tool_outcome_handling", score, 15, evidence, critical=score == 0))

    record_counts = [result["recordCount"] for result in tool_results if result["recordCount"] >= 0]
    count_claims = extract_record_count_claims(response)
    if count_claims and record_counts:
        allowed_counts = set(record_counts)
        allowed_counts.add(sum(record_counts))
        mismatches = [claim for claim in count_claims if claim not in allowed_counts]
        score = 0 if mismatches else 4
        metrics.append(
            metric(
                "record_count_accuracy",
                score,
                15,
                [
                    f"Response count claim(s): {count_claims}.",
                    f"Tool record count(s): {record_counts}.",
                ],
                critical=bool(mismatches),
            )
        )
    else:
        metrics.append(
            metric(
                "record_count_accuracy",
                None,
                15,
                ["No explicit record-count claim was found or no records were available."],
            )
        )

    source_values = collect_source_values(tool_results)
    source_dates = {value[:10] for value in source_values if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value)}
    execution_date = execution_time.date().isoformat() if execution_time else None
    allowed_dates = set(source_dates)
    if execution_date:
        allowed_dates.add(execution_date)
    response_dates = extract_iso_dates(response)
    if response_dates:
        ungrounded_dates = sorted(response_dates - allowed_dates)
        score = 0 if ungrounded_dates else 4
        metrics.append(
            metric(
                "date_value_fidelity",
                score,
                15,
                [
                    f"Response date(s): {sorted(response_dates)}.",
                    f"Allowed source/execution date(s): {sorted(allowed_dates)}.",
                ],
                critical=bool(ungrounded_dates),
            )
        )
    else:
        metrics.append(metric("date_value_fidelity", None, 15, ["No ISO date claim was found."]))

    pay_dates = collect_pay_dates(tool_results)
    relation_score: int | None = None
    relation_evidence: list[str] = []
    relation_critical = False
    if pay_dates and execution_time:
        today = execution_time.date()
        says_passed = bool(re.search(r"\b(?:pay|payable|payment) date\b.{0,80}\b(?:has )?passed\b", lowered))
        says_today = bool(re.search(r"\b(?:pay|payable|payment) date\b.{0,80}\b(?:is|equals) today\b", lowered))
        if says_passed:
            correct = all(value < today for value in pay_dates)
            relation_score = 4 if correct else 0
            relation_critical = not correct
            relation_evidence = [f"Pay date(s) {pay_dates} compared with {today}: passed={correct}."]
        elif says_today:
            correct = any(value == today for value in pay_dates)
            relation_score = 4 if correct else 0
            relation_critical = not correct
            relation_evidence = [f"Pay date(s) {pay_dates} compared with {today}: today={correct}."]
    metrics.append(
        metric(
            "date_relationship_accuracy",
            relation_score,
            15,
            relation_evidence or [f"No deterministic pay-date relationship claim was evaluated ({business_timezone})."],
            critical=relation_critical,
        )
    )

    grounded_text = " ".join(filter(None, [question or "", *source_values]))
    response_ids = extract_large_identifiers(response)
    grounded_ids = extract_large_identifiers(grounded_text)
    if response_ids:
        ungrounded_ids = sorted(response_ids - grounded_ids)
        score = 0 if ungrounded_ids else 4
        metrics.append(
            metric(
                "identifier_fidelity",
                score,
                10,
                [
                    f"Response identifier(s): {sorted(response_ids)}.",
                    f"Ungrounded identifier(s): {ungrounded_ids}.",
                ],
                critical=bool(ungrounded_ids),
            )
        )
    else:
        metrics.append(metric("identifier_fidelity", None, 10, ["No large identifier claim was found."]))

    status_mappings = rules.get("statusMappings", {}) if isinstance(rules, dict) else {}
    if "client paid" in lowered and status_mappings:
        mapped_values: list[bool] = []
        observed_statuses: list[str] = []
        for result in tool_results:
            for record in result["records"]:
                for key, value in record.items():
                    if "status" not in normalize_key(key) or value is None:
                        continue
                    code = str(value)
                    mapping = status_mappings.get(code)
                    if isinstance(mapping, dict) and isinstance(mapping.get("clientPaid"), bool):
                        mapped_values.append(mapping["clientPaid"])
                        observed_statuses.append(code)
        if mapped_values:
            response_denies_confirmation = any(
                phrase in lowered
                for phrase in ("could not be confirmed", "not client paid", "is not client paid")
            )
            expected_paid = all(mapped_values)
            correct = expected_paid != response_denies_confirmation
            metrics.append(
                metric(
                    "business_status_interpretation",
                    4 if correct else 0,
                    15,
                    [
                        f"Mapped status code(s): {observed_statuses}.",
                        f"Expected clientPaid={expected_paid}; response denies confirmation={response_denies_confirmation}.",
                    ],
                    critical=not correct,
                )
            )

    return metrics


def weighted_score(metrics: list[Metric]) -> float | None:
    applicable = [item for item in metrics if item.score is not None and item.weight > 0]
    if not applicable:
        return None
    earned = sum(item.score * item.weight for item in applicable)
    maximum = sum(4 * item.weight for item in applicable)
    return round(100 * earned / maximum, 2)


def build_agent_payload(
    correlation_id: str,
    question: str | None,
    final_response: str | None,
    tool_results: list[dict[str, Any]],
    execution_time: datetime | None,
    business_timezone: str,
    objective_metrics: list[Metric],
    rules: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evaluationVersion": "1.0",
        "correlationId": correlation_id,
        "question": question,
        "executionContext": {
            "timestamp": execution_time,
            "timezone": business_timezone,
        },
        "actualResults": tool_results,
        "finalResponse": final_response,
        "businessRules": rules,
        "objectiveMetrics": [asdict(item) for item in objective_metrics],
        "requestedAgentMetrics": [
            "factual_correctness",
            "business_rule_correctness",
            "completeness",
            "relevance",
            "groundedness",
            "internal_consistency",
            "clarity",
            "uncertainty_and_error_handling",
        ],
    }


def extract_agent_json(value: Any, max_depth: int = 8) -> dict[str, Any] | None:
    """Find the evaluator's JSON object inside common executor response wrappers."""
    current = unwrap_content_text(value)
    for _ in range(max_depth):
        current = decode_json_layers(current)
        if isinstance(current, dict) and ("metrics" in current or "criticalFailures" in current):
            return current
        if isinstance(current, dict):
            next_value = None
            for key in (
                "final_response",
                "finalResponse",
                "agent_response",
                "agentResponse",
                "response",
                "answer",
                "result",
                "data",
                "output",
                "content",
            ):
                if key in current:
                    next_value = current[key]
                    break
            if next_value is None:
                return None
            current = unwrap_content_text(next_value)
            continue
        if isinstance(current, list) and current:
            current = current[-1]
            continue
        return None
    return None


def required_agent_header(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing evaluator endpoint environment variable: {name}")
    return value


def find_token(value: Any, max_depth: int = 6) -> str | None:
    current = decode_json_layers(value)
    for _ in range(max_depth):
        if isinstance(current, str):
            token = current.strip().strip('"')
            return token or None
        if isinstance(current, dict):
            next_value = None
            for key in (
                "access_token",
                "accessToken",
                "token",
                "coin_token",
                "coinToken",
                "jwt",
                "data",
                "result",
            ):
                if key in current:
                    next_value = current[key]
                    break
            if next_value is None:
                return None
            current = decode_json_layers(next_value)
            continue
        return None
    return None


def fetch_authorization_coin() -> str:
    token_url = required_agent_header("EVALUATOR_TOKEN_URL")
    client_secret = required_agent_header("EVALUATOR_CLIENT_SECRET")
    body = json.dumps({"clientSecret": client_secret}).encode("utf-8")
    request = urllib.request.Request(
        token_url,
        data=body,
        headers={"Accept": "*/*", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=int(os.getenv("EVALUATOR_TOKEN_TIMEOUT", "30"))
        ) as response:
            raw_response = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"COIN token endpoint returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach the COIN token endpoint: {exc.reason}") from exc

    token = find_token(raw_response)
    if not token:
        raise RuntimeError("COIN token endpoint response did not contain a recognized token field")
    return token


def resolve_authorization_coin() -> str:
    token = os.getenv("EVALUATOR_AUTHORIZATION_COIN") or fetch_authorization_coin()
    token = token.strip()
    if not token:
        raise RuntimeError("EVALUATOR_AUTHORIZATION_COIN resolved to an empty value")
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def call_agent(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    executor_body = {
        "context": json.dumps(payload, ensure_ascii=True, default=json_default),
        "parts": [],
        "metadata": {},
        "state": {},
        "additional_tool_headers": {},
    }
    body = json.dumps(executor_body, ensure_ascii=True).encode("utf-8")
    evaluator_correlation_id = os.getenv("EVALUATOR_CORRELATION_ID") or str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Config-ID": required_agent_header("EVALUATOR_CONFIG_ID"),
        "X-Correlation-ID": evaluator_correlation_id,
        "X-Application-ID": required_agent_header("EVALUATOR_APPLICATION_ID"),
        "x-soeid": required_agent_header("EVALUATOR_SOEID"),
        "X-Authorization-Coin": resolve_authorization_coin(),
    }

    optional_headers = {
        "X-Country": os.getenv("EVALUATOR_COUNTRY"),
        "X-Region": os.getenv("EVALUATOR_REGION"),
    }
    headers.update({name: value for name, value in optional_headers.items() if value})
    token = os.getenv("EVALUATOR_AGENT_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(
            request, timeout=int(os.getenv("EVALUATOR_AGENT_TIMEOUT", "90"))
        ) as response:
            raw_response = decode_json_layers(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Evaluator agent returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach evaluator agent: {exc.reason}") from exc
    parsed = extract_agent_json(raw_response)
    if parsed is None:
        raise RuntimeError(
            "Could not find the evaluator JSON in the synchronous executor response. "
            "Ensure the evaluator returns the documented JSON schema."
        )
    return parsed


def normalize_agent_result(value: dict[str, Any]) -> dict[str, Any]:
    raw_metrics = value.get("metrics") or []
    normalized: list[dict[str, Any]] = []
    if isinstance(raw_metrics, dict):
        converted = []
        for name, metric_value in raw_metrics.items():
            if isinstance(metric_value, dict):
                converted.append(dict(metric_value, name=name))
            else:
                converted.append({"name": name, "score": metric_value, "evidence": []})
        raw_metrics = converted
    if not isinstance(raw_metrics, list):
        raise ValueError("Agent result metrics must be an array or object")

    for item in raw_metrics:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 4:
            continue
        evidence = item.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        normalized.append(
            {
                "name": item["name"],
                "score": score,
                "evidence": [str(entry) for entry in evidence],
            }
        )

    critical_failures = value.get("criticalFailures") or []
    if isinstance(critical_failures, str):
        critical_failures = [critical_failures]
    if not isinstance(critical_failures, list):
        critical_failures = []

    score = round(25 * sum(item["score"] for item in normalized) / len(normalized), 2) if normalized else None
    return {
        "score": score,
        "metrics": normalized,
        "criticalFailures": [str(item) for item in critical_failures],
        "summary": str(value.get("summary") or ""),
    }


def build_report(
    correlation_id: str,
    rows: list[dict[str, Any]],
    objective_metrics: list[Metric],
    tool_results: list[dict[str, Any]],
    question: str | None,
    final_response: str | None,
    execution_time: datetime | None,
    business_timezone: str,
    agent_result: dict[str, Any] | None,
) -> dict[str, Any]:
    objective_score = weighted_score(objective_metrics)
    objective_failures = [
        f"{item.name}: {'; '.join(item.evidence)}"
        for item in objective_metrics
        if item.critical and item.status == "FAIL"
    ]
    agent_score = agent_result.get("score") if agent_result else None
    agent_failures = agent_result.get("criticalFailures", []) if agent_result else []
    critical_failures = objective_failures + agent_failures

    if objective_score is not None and agent_score is not None:
        overall_score = round(
            objective_score * DEFAULT_CODE_WEIGHT + agent_score * DEFAULT_AGENT_WEIGHT, 2
        )
        if critical_failures:
            result = "FAIL"
        elif overall_score >= 80:
            result = "PASS"
        elif overall_score >= 65:
            result = "REVIEW"
        else:
            result = "FAIL"
    else:
        overall_score = None
        result = "AWAITING_AGENT" if objective_score is not None else "INSUFFICIENT_DATA"

    return {
        "evaluationVersion": "1.0",
        "correlationId": correlation_id,
        "result": result,
        "overallScore": overall_score,
        "objectiveScore": objective_score,
        "agentScore": agent_score,
        "weights": {"objective": DEFAULT_CODE_WEIGHT, "agent": DEFAULT_AGENT_WEIGHT},
        "criticalFailures": critical_failures,
        "executionContext": {
            "timestamp": execution_time,
            "timezone": business_timezone,
            "auditRowCount": len(rows),
        },
        "question": question,
        "finalResponse": final_response,
        "toolSummary": [
            {
                "toolName": item["toolName"],
                "status": item["toolStatus"],
                "recordCount": item["recordCount"],
                "errorCount": len(item["errors"]),
            }
            for item in tool_results
        ],
        "objectiveMetrics": [asdict(item) for item in objective_metrics],
        "agentEvaluation": agent_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--correlation-id", help="x_correlation_id to read from PostgreSQL")
    source.add_argument("--rows-json", help="JSON file containing exported/synthetic audit rows")
    parser.add_argument(
        "--table",
        default=os.getenv("VEGA_AUDIT_TABLE", DEFAULT_TABLE),
        help=f"Audit table in schema.table form (default: {DEFAULT_TABLE})",
    )
    parser.add_argument("--rules", help="Optional JSON file containing approved business mappings")
    parser.add_argument("--agent-url", default=os.getenv("EVALUATOR_AGENT_URL"))
    parser.add_argument("--agent-result", help="Existing evaluator-agent JSON result to merge")
    parser.add_argument("--agent-payload-out", help="Write the evaluator-agent request JSON here")
    parser.add_argument("--output", default="evaluation_report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.rows_json:
            rows = load_json(args.rows_json)
            if not isinstance(rows, list):
                raise ValueError("--rows-json must contain a JSON array")
            correlation_id = str(
                next((row.get("x_correlation_id") for row in rows if row.get("x_correlation_id")), "fixture")
            )
        else:
            correlation_id = args.correlation_id
            rows = read_audit_rows(correlation_id, args.table)

        if not rows:
            raise RuntimeError(f"No audit rows found for correlation ID {correlation_id}")

        rules = load_json(args.rules) if args.rules else {}
        question = first_nonempty(rows, "user_message")
        final_response = select_final_response(rows)
        tool_results, parse_warnings = parse_tool_results(rows)
        execution_time, business_timezone = resolve_execution_time(rows)
        objective_metrics = evaluate_objective(
            question,
            final_response,
            tool_results,
            execution_time,
            business_timezone,
            parse_warnings,
            rules,
        )
        agent_payload = build_agent_payload(
            correlation_id,
            question,
            final_response,
            tool_results,
            execution_time,
            business_timezone,
            objective_metrics,
            rules,
        )
        if args.agent_payload_out:
            write_json(args.agent_payload_out, agent_payload)

        agent_result = None
        if args.agent_result:
            agent_result = normalize_agent_result(load_json(args.agent_result))
        elif args.agent_url:
            agent_result = normalize_agent_result(call_agent(args.agent_url, agent_payload))

        report = build_report(
            correlation_id,
            rows,
            objective_metrics,
            tool_results,
            question,
            final_response,
            execution_time,
            business_timezone,
            agent_result,
        )
        write_json(args.output, report)
        print(
            json.dumps(
                {
                    "result": report["result"],
                    "overallScore": report["overallScore"],
                    "objectiveScore": report["objectiveScore"],
                    "agentScore": report["agentScore"],
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
