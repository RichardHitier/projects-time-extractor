"""Convert DATA/webhook_log.jsonl to DATA/webhook.csv.

The input file is produced by webhook_receiver.py while discovering Pomofocus
webhook calls. The output follows the local pomofocus.csv schema:
    date, project, task, minutes, startTime, endTime

Only completed or paused pomodoro work segments are exported. Other events are
kept in the JSONL protocol log but ignored for CSV ingestion.
"""
import csv
import json
import os
from datetime import datetime

from config import load_config

_config = load_config()
LOG = os.path.join(_config["DATA_DIR"], "webhook_log.jsonl")
OUT = os.path.join(_config["DATA_DIR"], "webhook.csv")
COLS = ["date", "project", "task", "minutes", "startTime", "endTime"]
EXPORT_TYPES = {"finish", "pause"}


def _from_epoch_ms(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000)


def payload_to_row(payload):
    if not isinstance(payload, dict):
        return None
    if payload.get("round") != "pomodoro":
        return None
    if payload.get("type") not in EXPORT_TYPES:
        return None

    seconds = payload.get("seconds") or 0
    minutes = round(seconds / 60)
    if minutes < 1:
        return None

    session_start = _from_epoch_ms(payload.get("session_start"))
    session_end = _from_epoch_ms(payload.get("session_end"))
    if session_start is None or session_end is None:
        return None

    return {
        "date": session_start.strftime("%Y%m%d"),
        "project": payload.get("project", ""),
        "task": payload.get("task", ""),
        "minutes": minutes,
        "startTime": session_start.strftime("%H:%M"),
        "endTime": session_end.strftime("%H:%M"),
    }


def iter_rows(log_path=LOG):
    with open(log_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSON line {line_no}: {exc}")
                continue

            row = payload_to_row(event.get("json"))
            if row:
                yield row


def deduplicate_rows(rows):
    seen = {}
    for row in rows:
        key = (row["date"], row["startTime"], row["project"], row["task"])
        if key not in seen or row["endTime"] > seen[key]["endTime"]:
            seen[key] = row
    return sorted(seen.values(), key=lambda row: (row["date"], row["startTime"]))


def write_csv(rows, out_path=OUT):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not os.path.exists(LOG):
        raise SystemExit(f"Webhook log not found: {LOG}")

    rows = deduplicate_rows(iter_rows(LOG))
    write_csv(rows, OUT)
    print(f"{len(rows)} lignes -> {OUT}")


if __name__ == "__main__":
    main()
