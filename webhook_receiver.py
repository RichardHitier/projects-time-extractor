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

from flask import Flask, Response, jsonify, request

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

BILLABLE_PROJECTS = {p.lower() for p in _config.get("BILLABLE_PROJECTS", [])}
BILLABLE_MAX_HOURS = 4

app = Flask(__name__)

# Tâche en cours (trame "start" pas encore suivie de "pause"/"finish").
# Process gunicorn à un seul worker (-w 1) : pas de souci de cohérence entre workers.
CURRENT_TASK = None


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


def merge_contiguous_sessions(rows):
    """Collapse back-to-back sessions (same date/project/task, endTime ==
    next startTime) into a single row each, like report.csv already does on
    the pomofocus.io side."""
    rows = sorted(rows, key=lambda row: (row["date"], row["startTime"]))
    merged = []
    for row in rows:
        if merged:
            prev = merged[-1]
            if (
                prev["date"] == row["date"]
                and prev["project"] == row["project"]
                and prev["task"] == row["task"]
                and prev["endTime"] == row["startTime"]
            ):
                prev["minutes"] = int(prev["minutes"]) + int(row["minutes"])
                prev["endTime"] = row["endTime"]
                continue
        merged.append(dict(row))
    return merged


def upsert_csv_row(row, csv_path=None):
    if csv_path is None:
        csv_path = CSV_PATH
    rows = _read_csv_rows(csv_path)
    key = (row["date"], row["startTime"], row["project"], row["task"])

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
            _write_csv_rows(merge_contiguous_sessions(rows), csv_path)
            return

    rows.append(row)
    _write_csv_rows(merge_contiguous_sessions(rows), csv_path)


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


def _update_current_task(payload):
    global CURRENT_TASK
    if not isinstance(payload, dict) or payload.get("round") != "pomodoro":
        return

    event_type = payload.get("type")
    if event_type == "start":
        session_start = payload.get("session_start")
        start_dt = _from_epoch_ms(session_start)
        if start_dt is None:
            return
        CURRENT_TASK = {
            "date": start_dt.strftime("%Y%m%d"),
            "project": payload.get("project", ""),
            "task": payload.get("task", ""),
            "start_ms": session_start,
        }
    elif event_type in EXPORT_TYPES:
        CURRENT_TASK = None


def current_task_row():
    if CURRENT_TASK is None:
        return None
    start_dt = _from_epoch_ms(CURRENT_TASK["start_ms"])
    now = datetime.now()
    minutes = max(0, round((now - start_dt).total_seconds() / 60))
    return {
        "date": CURRENT_TASK["date"],
        "project": CURRENT_TASK["project"],
        "task": CURRENT_TASK["task"],
        "minutes": minutes,
        "startTime": start_dt.strftime("%H:%M"),
        "endTime": now.strftime("%H:%M"),
    }


def _row_is_billable(row):
    project = (row.get("project") or "").split("_", 1)[0].strip().lower()
    return project in BILLABLE_PROJECTS


def billable_minutes(rows, day):
    total = 0
    for row in rows:
        if row.get("date") != day:
            continue
        if not _row_is_billable(row):
            continue
        total += int(row.get("minutes") or 0)
    return total


def billable_hours(day=None):
    if day is None:
        day = datetime.now().strftime("%Y%m%d")
    return billable_minutes(_read_csv_rows(CSV_PATH), day) / 60


def _format_hm(hours):
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    return f"{h}:{m:02d}"


def render_billable_svg(hours, max_hours=BILLABLE_MAX_HOURS):
    width, height = 640, 110
    bar_x, bar_y, bar_w, bar_h = 20, 56, 600, 32
    corner_radius = 6
    ratio = max(0, min(hours / max_hours, 1)) if max_hours else 0
    fill_w = (bar_w - 6) * ratio
    hours_label = _format_hm(hours)
    max_hours_label = _format_hm(max_hours)

    ticks = []
    for h in range(1, max_hours):
        tick_x = bar_x + bar_w * h / max_hours
        ticks.append(
            f'<line x1="{tick_x:.1f}" y1="{bar_y - 4}" x2="{tick_x:.1f}" '
            f'y2="{bar_y + bar_h + 4}" stroke="#383835" stroke-width="1" opacity=".6"/>'
        )

    fill_rect = ""
    if fill_w > 0:
        fill_rect = (
            f'<rect x="{bar_x + 3}" y="{bar_y + 3}" width="{fill_w:.1f}" '
            f'height="{bar_h - 6}" rx="{corner_radius}" fill="#3987e5"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{hours_label} facturables aujourd'hui sur {max_hours_label}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{bar_x}" y="30" font-family="system-ui, sans-serif" font-size="20" fill="#ffffff">
    {hours_label}<tspan fill="#c3c2b7" font-size="14"> facturables aujourd'hui / {max_hours_label}</tspan>
  </text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{corner_radius}" fill="#184f95"/>
  {fill_rect}
  {"".join(ticks)}
</svg>"""


def persist_event(event):
    _write_event(event)
    payload = event.get("json")
    _update_current_task(payload)
    row = payload_to_csv_row(payload)
    if row:
        upsert_csv_row(row)
        print(f"CSV upsert: {CSV_PATH} {row}", flush=True)


@app.get("/health")
def health():
    return "ok\n", 200


VIEW_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Pomofocus webhook — live</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee; }}
  h1 {{ font-size: 1.1rem; font-weight: normal; color: #999; }}
  h2 {{ font-size: .8rem; font-weight: normal; text-transform: uppercase; color: #999; margin: 0 0 .5rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: .4rem .8rem; border-bottom: 1px solid #333; }}
  th {{ color: #999; font-weight: normal; text-transform: uppercase; font-size: .75rem; }}
  tr.new {{ animation: flash 2s ease-out; }}
  @keyframes flash {{ from {{ background: #2a5; }} to {{ background: transparent; }} }}
  #current-box {{
    border: 1px solid #2a5; border-radius: 6px; padding: .8rem 1rem; margin-bottom: 1.5rem;
  }}
  #current-box.empty {{ border-color: #333; color: #666; font-style: italic; }}
  #current-box table {{ margin-top: .3rem; }}
  .dot {{ display: inline-block; width: .5rem; height: .5rem; border-radius: 50%; background: #2a5;
          animation: pulse 1.5s ease-in-out infinite; margin-right: .4rem; }}
  @keyframes pulse {{ 50% {{ opacity: .3; }} }}
  #status {{ color: #666; font-size: .8rem; margin-top: 1rem; }}
  #billable {{ display: block; margin-bottom: 1.5rem; max-width: 100%; }}
</style>
</head>
<body>
<h2>En cours</h2>
<div id="current-box" class="empty">aucune tâche en cours</div>

<h2>Facturable aujourd'hui</h2>
<img id="billable" src="{billable_url}" alt="heures facturables">

<h1>pomofocus_webhook.csv — mis à jour toutes les 3s (plus récent en haut)</h1>
<table>
  <thead><tr><th>Date</th><th>Projet</th><th>Tâche</th><th>Min</th><th>Début</th><th>Fin</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="status">chargement...</div>
<script>
const API_URL = "{api_url}";
const BILLABLE_URL = "{billable_url}";
let known = new Set();

function rowHtml(r) {{
  return `<td>${{r.date}}</td><td>${{r.project}}</td><td>${{r.task}}</td>` +
         `<td>${{r.minutes}}</td><td>${{r.startTime}}</td><td>${{r.endTime}}</td>`;
}}

async function poll() {{
  let data;
  try {{
    const res = await fetch(API_URL, {{cache: "no-store"}});
    data = await res.json();
  }} catch (e) {{
    document.getElementById("status").textContent = "erreur de connexion";
    return;
  }}

  const box = document.getElementById("current-box");
  if (data.current) {{
    box.className = "";
    box.innerHTML = `<span class="dot"></span>${{data.current.project}} — ${{data.current.task}}` +
      `<table><tbody><tr>${{rowHtml(data.current)}}</tr></tbody></table>`;
  }} else {{
    box.className = "empty";
    box.textContent = "aucune tâche en cours";
  }}

  const tbody = document.getElementById("rows");
  tbody.innerHTML = "";
  for (const r of data.rows) {{
    const key = r.date + r.startTime + r.project + r.task;
    const tr = document.createElement("tr");
    if (!known.has(key)) tr.className = "new";
    tr.innerHTML = rowHtml(r);
    tbody.appendChild(tr);
    known.add(key);
  }}
  document.getElementById("status").textContent =
    data.rows.length + " lignes — dernière vérification " + new Date().toLocaleTimeString();

  document.getElementById("billable").src = BILLABLE_URL + "?t=" + Date.now();
}}

poll();
setInterval(poll, 3000);
</script>
</body>
</html>
"""


@app.get("/view", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/view")
def view(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    return VIEW_HTML.format(api_url=f"{prefix}/api/rows", billable_url=f"{prefix}/billable.svg")


@app.get("/billable.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/billable.svg")
def billable_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    svg = render_billable_svg(billable_hours())
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/rows", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/api/rows")
def api_rows(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    rows = _read_csv_rows(CSV_PATH)
    rows.sort(key=lambda r: (r["date"], r["startTime"]), reverse=True)
    return jsonify({"rows": rows, "current": current_task_row()})


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
