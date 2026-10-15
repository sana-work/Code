"""Reference-policy checks for the date-display update, not live model trials.

The earlier harness and reports intentionally retain their original snapshot.
This small oracle exercises the new exception without rewriting that history.
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

import pytest
import yaml


ZERO_TIME = re.compile(
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})[ T]?00:00:00"
    r"(?:\.0+)?(?P<zone>Z|[+-][0-9]{2}:[0-9]{2})?"
)


def display_date(value, *, registered_date_field):
    if not registered_date_field or not isinstance(value, str):
        return value
    match = ZERO_TIME.fullmatch(value)
    if match is None:
        return value
    calendar_date = match["date"]
    zone = match["zone"] or ""
    try:
        date.fromisoformat(calendar_date)
        datetime.fromisoformat(calendar_date + "T00:00:00" + zone.replace("Z", "+00:00"))
    except ValueError:
        return value
    return calendar_date


@pytest.mark.parametrize("value", [
    "2026-01-01 00:00:00.000",
    "2026-01-01T00:00:00.000Z",
    "2026-01-0100:00:00.000",
    "2026-01-01 00:00:00",
    "2026-01-01T00:00:00Z",
    "2026-01-01T00:00:00.000000000Z",
    "2026-01-01T00:00:00.000+05:30",
    "2026-01-01T00:00:00.000-04:00",
])
def test_zero_time_is_date_only_without_timezone_conversion(value):
    assert display_date(value, registered_date_field=True) == "2026-01-01"


@pytest.mark.parametrize("value", [
    "2026-01-01", "2026-01-01T01:00:00.000Z",
    "2026-01-01T00:01:00.000Z", "2026-01-01T00:00:01.000Z",
    "2026-01-01T00:00:00.001Z", "2026-01-01T00:00:00.000000001Z",
    "2026-02-30T00:00:00.000Z", "2026-01-01T00:00:00.000+99:99",
    "01/01/2026 00:00:00.000", "2026-01-01 00:00:00.000,",
    "Payment dated 2026-01-01 00:00:00.000", "00:00:00.000",
    "", "null", "null grandson", "0000010000", None,
])
def test_other_values_are_not_cleaned_or_truncated(value):
    assert display_date(value, registered_date_field=True) == value


def test_date_looking_identifier_or_free_text_is_unchanged():
    value = "2026-01-01 00:00:00.000"
    assert display_date(value, registered_date_field=False) == value


def test_leap_day_requires_valid_calendar_date():
    assert display_date("2024-02-29T00:00:00Z", registered_date_field=True) == "2024-02-29"
    assert display_date("2026-02-29T00:00:00Z", registered_date_field=True) == "2026-02-29T00:00:00Z"


@pytest.mark.parametrize("indices", [list(range(8)), [0, 1, 2, 4, 6, 7]])
def test_full_and_compact_display_keep_raw_cache_and_other_cells(indices):
    source = {
        "columns": ["Event ID", "Payment Date", "Timestamp", "Narrative",
                    "Cash Amount", "Currency", "Blank", "Record Date"],
        "rows": [{"cells": ["0001000001", "2026-01-01 00:00:00.000",
                            "2026-01-01T00:00:00.001Z", "2026-01-01 00:00:00.000",
                            "100.00", "CAD", "", "2025-12-05T00:00:00Z"]}],
    }
    before = deepcopy(source)
    date_indices = {1, 2, 7}
    presented = {
        "columns": [source["columns"][i] for i in indices],
        "rows": [{"cells": [display_date(row["cells"][i], registered_date_field=i in date_indices)
                             for i in indices]} for row in source["rows"]],
    }
    assert source == before
    assert presented["columns"] == [source["columns"][i] for i in indices]
    assert presented["rows"][0]["cells"] == [
        "2026-01-01" if i == 1 else "2025-12-05" if i == 7 else before["rows"][0]["cells"][i]
        for i in indices
    ]
    assert len(presented["rows"]) == len(source["rows"])
    assert len(presented["rows"][0]["cells"]) == len(presented["columns"])


def test_updated_prompt_has_exception_without_changing_ui_contract():
    root = Path(__file__).resolve().parent
    current = yaml.safe_load((root.parent / "Universal_Chat_Single_Agent_System_Prompt.yaml").read_text())
    original = yaml.safe_load((root / "reports" / "prompt_snapshot.yaml").read_text())
    assert current["output_schema"] == original["output_schema"]
    assert hashlib.sha256(current["output_schema"].encode()).hexdigest() == (
        "c8a46ceac9cc5d2d733778373cec24f4c1cd6a5c2075a6a5a1e7a80f7867a51f"
    )
    assert current["response_type"] == "JSON" and current["output_key"] == "schema"
    assert json.loads(current["output_schema"])["title"] == "UniversalChatExecutionSchema"
    instruction = current["instruction"]
    assert "ZERO_TIME_DATE_DISPLAY" in instruction
    assert "FULL_TABLE views" in instruction and "cached table-only follow-ups" in instruction
    assert "raw source and cached values remain intact" in instruction
    assert "2026-01-0100:00:00.000" in instruction
