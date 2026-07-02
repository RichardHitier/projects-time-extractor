"""Capture Pomofocus webhook calls and write a Pomofocus-like CSV.

Every request is logged as JSON Lines to DATA/webhook_log.jsonl and echoed to
stdout. Valid Pomofocus work events are also upserted into
DATA/pomofocus_webhook.csv with the same columns as DATA/pomofocus.csv.

Run locally:
    python webhook_receiver.py
    cloudflared tunnel --url http://localhost:5000

Then configure Pomofocus with:
    https://xxxxx.trycloudflare.com/

Set WEBHOOK_SECRET to use an unguessable path:
    WEBHOOK_SECRET=my-secret python webhook_receiver.py
    https://xxxxx.trycloudflare.com/my-secret
"""
import csv
import json
import os
from datetime import datetime, timezone

from flask import Flask, request

from config import load_config

_config = load_config()
DATA_DIR = _config["DATA_DIR"]
LOG_PATH = os.path.join(DATA_DIR, "webhook_log.jsonl")
CSV_PATH = os.environ.get(
    "POMOFOCUS_WEBHOOK_CSV",
    os.path.join(DATA_DIR, "pomofocus_webhook.csv"),
)
CSV_COLUMNS = ["date", "project", "task", "minutes", "startTime", "endTime"]
EXPORT_TYPES = {"finish", "pause"}
SECRET = os.environ.get("WEBHOOK_SECRET", "").strip("/")
PORT = int(os.environ.get("WEBHOOK_PORT", "5000"))

app = Flask(__name__)


def _from_epoch_ms(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000)


def payload_to_csv_row(payload):
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


def _read_csv_rows(csv_path):
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv_rows(rows, csv_path):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    rows = sorted(rows, key=lambda row: (row["date"], row["startTime"], row["project"], row["task"]))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def upsert_csv_row(row, csv_path=None):
    if csv_path is None:
        csv_path = CSV_PATH
    rows = _read_csv_rows(csv_path)
    key = (row["date"], row["startTime"], row["project"], row["task"])
    replaced = False

    for index, existing in enumerate(rows):
        existing_key = (
            existing["date"],
            existing["startTime"],
            existing["project"],
            existing["task"],
        )
        if existing_key == key:
            if row["endTime"] >= existing["endTime"]:
                rows[index] = row
            replaced = True
            break

    if not replaced:
        rows.append(row)

    _write_csv_rows(rows, csv_path)


def _record(req):
    raw = req.get_data()
    parsed = req.get_json(force=True, silent=True)
    form = req.form.to_dict(flat=False) if req.form else None
    return {
        "received_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "received_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "remote_addr": req.headers.get("X-Forwarded-For", req.remote_addr),
        "method": req.method,
        "scheme": req.headers.get("X-Forwarded-Proto", req.scheme),
        "host": req.headers.get("X-Forwarded-Host", req.host),
        "path": req.path,
        "full_path": req.full_path,
        "url": req.url,
        "args": req.args.to_dict(flat=False),
        "headers": dict(req.headers),
        "content_type": req.content_type,
        "content_length": req.content_length,
        "body_raw": raw.decode("utf-8", errors="replace"),
        "json": parsed,
        "form": form,
    }


def _write_event(event):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=True)
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def persist_event(event):
    _write_event(event)
    row = payload_to_csv_row(event.get("json"))
    if row:
        upsert_csv_row(row)
        print(f"CSV upsert: {CSV_PATH} {row}", flush=True)


@app.get("/health")
def health():
    return "ok\n", 200


@app.route("/", defaults={"secret_path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.route("/<path:secret_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def hook(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404

    event = _record(request)
    persist_event(event)
    return "OK\n", 200


if __name__ == "__main__":
    print(f"Logging Pomofocus webhooks to {LOG_PATH}")
    print(f"Writing Pomofocus-like CSV to {CSV_PATH}")
    endpoint = f"/{SECRET}" if SECRET else "/"
    print(f"Endpoint path: {endpoint}  (set WEBHOOK_SECRET to require a secret path)")
    print(f"Listening on http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=True)
