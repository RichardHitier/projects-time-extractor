import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webhook_log_to_csv import deduplicate_rows, payload_to_row


def test_payload_to_row_exports_finished_pomodoro():
    row = payload_to_row({
        "round": "pomodoro",
        "type": "finish",
        "seconds": 1500,
        "session_start": 1711962000000,
        "session_end": 1711963500000,
        "project": "calipso",
        "task": "#42 auth: tests",
    })

    assert row == {
        "date": "20240401",
        "project": "calipso",
        "task": "#42 auth: tests",
        "minutes": 25,
        "startTime": "11:00",
        "endTime": "11:25",
    }


def test_payload_to_row_ignores_non_work_events():
    assert payload_to_row({"round": "short_break", "type": "finish"}) is None
    assert payload_to_row({"round": "pomodoro", "type": "start"}) is None
    assert payload_to_row({"round": "pomodoro", "type": "finish", "seconds": 10}) is None


def test_deduplicate_rows_keeps_latest_end_time():
    rows = [
        {"date": "20240401", "project": "p", "task": "t", "minutes": 5, "startTime": "11:00", "endTime": "11:05"},
        {"date": "20240401", "project": "p", "task": "t", "minutes": 10, "startTime": "11:00", "endTime": "11:10"},
    ]

    assert deduplicate_rows(rows) == [rows[1]]
