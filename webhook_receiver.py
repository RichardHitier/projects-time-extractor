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
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, jsonify, request

from config import load_config, load_projects

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
BILLABLE_WEEKS_SHOWN = 12  # /weeks : nombre de semaines les plus récentes affichées

_FR_WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]

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


def current_week_bounds(today=None):
    """Monday and Sunday (date objects) of the week containing `today`."""
    if today is None:
        today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def billable_hours_for_days(monday, last_day, rows):
    """Billable hours per day from `last_day` down to `monday` (most recent
    first), as (day_label, hours) pairs."""
    days = []
    day = last_day
    while day >= monday:
        hours = billable_minutes(rows, day.strftime("%Y%m%d")) / 60
        days.append((_FR_WEEKDAYS[day.weekday()], hours))
        day -= timedelta(days=1)
    return days


def billable_hours_for_week(today=None):
    """Billable hours per elapsed day of the current week (Monday..today),
    most recent first, as (day_label, hours) pairs."""
    if today is None:
        today = datetime.now().date()
    monday, _ = current_week_bounds(today)
    return billable_hours_for_days(monday, today, _read_csv_rows(CSV_PATH))


def recent_billable_weeks(today=None, count=BILLABLE_WEEKS_SHOWN):
    """The `count` most recent weeks, most recent first, as
    (monday, sunday, day_hours) tuples. The current week stops at `today`;
    completed weeks span Monday..Sunday. Empty weeks are kept."""
    if today is None:
        today = datetime.now().date()
    rows = _read_csv_rows(CSV_PATH)
    monday, _ = current_week_bounds(today)
    last_day = today
    weeks = []
    for _ in range(count):
        sunday = monday + timedelta(days=6)
        weeks.append((monday, sunday, billable_hours_for_days(monday, last_day, rows)))
        monday -= timedelta(days=7)
        last_day = monday + timedelta(days=6)  # semaine précédente : dimanche
    return weeks


def _fr_week_range(monday, sunday):
    """French label like 'Semaine du 23 au 29 juin 2026', collapsing the
    start's month/year when identical to the end's."""
    if monday.year != sunday.year:
        start = f"{monday.day} {_FR_MONTHS[monday.month - 1]} {monday.year}"
    elif monday.month != sunday.month:
        start = f"{monday.day} {_FR_MONTHS[monday.month - 1]}"
    else:
        start = str(monday.day)
    end = f"{sunday.day} {_FR_MONTHS[sunday.month - 1]} {sunday.year}"
    return f"Semaine du {start} au {end}"


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
    title = f"FACTURABLE AUJOURD'HUI: {hours_label} / {max_hours}h"

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
            f'height="{bar_h - 6}" rx="{corner_radius}" fill="#9d9d93"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{bar_x}" y="30" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{corner_radius}" fill="#2e2e2b"/>
  {fill_rect}
  {"".join(ticks)}
</svg>"""


BILLABLE_WEEK_MAX_HOURS = 20


def render_week_svg(day_hours, max_hours=BILLABLE_MAX_HOURS, week_max_hours=BILLABLE_WEEK_MAX_HOURS):
    """Render a "SEMAINE : total / Nh" header, then one bar per
    (day_label, hours) pair, most recent first.

    Bars past `max_hours` overflow past a boundary marker (in a distinct
    color) instead of being clamped, up to a capped overflow lane.
    """
    width = 640
    row_h, row_gap, header_h = 22, 12, 30
    top = header_h + row_gap
    label_x, bar_x, bar_w, overflow_max = 20, 110, 380, 60
    corner_radius = 5
    inset = 3
    height = top + len(day_hours) * (row_h + row_gap)
    total_hours = sum(hours for _, hours in day_hours)
    title = f"SEMAINE : {_format_hm(total_hours)} / {week_max_hours}h"

    rows_svg = []
    for i, (label, hours) in enumerate(day_hours):
        y = top + i * (row_h + row_gap)
        ratio = hours / max_hours if max_hours else 0
        inner_h = row_h - 2 * inset
        fill_w = (bar_w - 2 * inset) * min(ratio, 1)
        fill_rect = ""
        if fill_w > 0:
            fill_rect = (
                f'<rect x="{bar_x + inset}" y="{y + inset}" width="{fill_w:.1f}" '
                f'height="{inner_h}" rx="{corner_radius}" fill="#9d9d93"/>'
            )
        overflow_rect = ""
        if ratio > 1:
            overflow_w = overflow_max * min(ratio - 1, 1)
            overflow_rect = (
                f'<rect x="{bar_x + bar_w + inset}" y="{y + inset}" width="{overflow_w:.1f}" '
                f'height="{inner_h}" rx="{corner_radius}" fill="#d9a441"/>'
            )
        rows_svg.append(f'''
  <text x="{label_x}" y="{y + row_h - 6}" font-family="system-ui, sans-serif" font-size="13" fill="#c3c2b7">{label}</text>
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{row_h}" rx="{corner_radius}" fill="#2e2e2b"/>
  {fill_rect}
  <line x1="{bar_x + bar_w}" y1="{y - 2}" x2="{bar_x + bar_w}" y2="{y + row_h + 2}" stroke="#c3c2b7" stroke-width="2"/>
  {overflow_rect}
  <text x="{bar_x + bar_w + overflow_max + 12}" y="{y + row_h - 6}" font-family="system-ui, sans-serif" font-size="13" fill="#ffffff">{_format_hm(hours)}</text>''')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{label_x}" y="20" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  {"".join(rows_svg)}
</svg>"""


# ── Activité par projet (couleurs identiques à `timer day-bars`) ──────────────
ACTIVITY_MAX_HOURS = 8

# tab20 + tab20b (40 couleurs), figées depuis matplotlib pour rester identiques à
# core.plots._project_color_map sans embarquer matplotlib dans le conteneur.
ACTIVITY_PALETTE = [
    "#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728",
    "#ff9896", "#9467bd", "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2",
    "#7f7f7f", "#c7c7c7", "#bcbd22", "#dbdb8d", "#17becf", "#9edae5", "#393b79",
    "#5254a3", "#6b6ecf", "#9c9ede", "#637939", "#8ca252", "#b5cf6b", "#cedb9c",
    "#8c6d31", "#bd9e39", "#e7ba52", "#e7cb94", "#843c39", "#ad494a", "#d6616b",
    "#e7969c", "#7b4173", "#a55194", "#ce6dbd", "#de9ed6",
]


def _project_config_colors():
    """{lowercased pom_project name: color} from projects-config.yml, matching
    core.plots._project_color_map (pro's [PRO, COLIBRI] → both get pro's red)."""
    colors = {}
    for data in (load_projects() or {}).values():
        if not isinstance(data, dict) or not data.get("color"):
            continue
        pom = data.get("pom_project")
        for name in ([pom] if isinstance(pom, str) else (pom or [])):
            colors[name.lower()] = data["color"]
    return colors


_PROJECT_CONFIG_COLORS = _project_config_colors()


def _project_prefix(project):
    """Top-level project = part before the first '_', as _row_is_billable does."""
    return (project or "").split("_", 1)[0].strip().lower()


def project_color(prefix):
    """Same rule as core.plots._project_color_map: config color when defined,
    else a stable md5 hash into the tab20+tab20b palette."""
    if prefix in _PROJECT_CONFIG_COLORS:
        return _PROJECT_CONFIG_COLORS[prefix]
    idx = int(hashlib.md5(prefix.encode()).hexdigest(), 16) % len(ACTIVITY_PALETTE)
    return ACTIVITY_PALETTE[idx]


def _ordered_projects(prefixes):
    """Stable order: billable projects first (alpha), then the rest (alpha)."""
    prefixes = set(prefixes)
    billable = sorted(p for p in prefixes if p in BILLABLE_PROJECTS)
    other = sorted(p for p in prefixes if p not in BILLABLE_PROJECTS)
    return billable + other


def activity_by_project(rows, day):
    """{project_prefix: minutes} for `day`, all projects except nan/empty."""
    totals = {}
    for row in rows:
        if row.get("date") != day:
            continue
        prefix = _project_prefix(row.get("project"))
        if not prefix or prefix == "nan":
            continue
        totals[prefix] = totals.get(prefix, 0) + int(row.get("minutes") or 0)
    return totals


def _activity_segments(totals, x0, inner_w, inner_y, inner_h, max_hours):
    """Colored <rect> segments for one stacked bar, stable order, clamped to
    the bar width (a day past `max_hours` is cut rather than overflowing)."""
    segs = []
    x, x_max = x0, x0 + inner_w
    for prefix in _ordered_projects(totals):
        seg_w = min(inner_w * (totals[prefix] / 60 / max_hours), x_max - x)
        if seg_w <= 0:
            continue
        segs.append(
            f'<rect x="{x:.1f}" y="{inner_y}" width="{seg_w:.1f}" '
            f'height="{inner_h}" fill="{project_color(prefix)}"/>'
        )
        x += seg_w
    return "".join(segs)


def render_activity_svg(totals, max_hours=ACTIVITY_MAX_HOURS):
    """Single stacked horizontal bar of the day's activity by project, same
    box/geometry as render_billable_svg, scaled to `max_hours`."""
    width, height = 640, 110
    bar_x, bar_y, bar_w, bar_h = 20, 56, 600, 32
    corner_radius = 6
    inner_x, inner_w, inner_y, inner_h = bar_x + 3, bar_w - 6, bar_y + 3, bar_h - 6
    title = f"ACTIVITÉ AUJOURD'HUI : {_format_hm(sum(totals.values()) / 60)}"
    ticks = "".join(
        f'<line x1="{bar_x + bar_w * h / max_hours:.1f}" y1="{bar_y - 4}" '
        f'x2="{bar_x + bar_w * h / max_hours:.1f}" y2="{bar_y + bar_h + 4}" '
        f'stroke="#383835" stroke-width="1" opacity=".6"/>'
        for h in range(1, max_hours)
    )
    segs = _activity_segments(totals, inner_x, inner_w, inner_y, inner_h, max_hours)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <defs><clipPath id="actbar"><rect x="{inner_x}" y="{inner_y}" width="{inner_w}" height="{inner_h}" rx="{corner_radius}"/></clipPath></defs>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{bar_x}" y="30" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{corner_radius}" fill="#2b2b28"/>
  <g clip-path="url(#actbar)">{segs}</g>
  {ticks}
</svg>"""


def render_activity_week_svg(days, max_hours=ACTIVITY_MAX_HOURS):
    """One stacked activity bar per day (most recent first). Row geometry
    matches render_week_svg so the two week charts line up side by side."""
    width = 640
    row_h, row_gap, header_h = 22, 12, 30
    top = header_h + row_gap
    label_x, bar_x, bar_w = 20, 110, 380
    corner_radius, inset = 5, 3
    height = top + len(days) * (row_h + row_gap)
    week_total = sum(sum(t.values()) for _, t in days) / 60
    title = f"ACTIVITÉ SEMAINE : {_format_hm(week_total)}"
    rows_svg = []
    for i, (label, totals) in enumerate(days):
        y = top + i * (row_h + row_gap)
        inner_x, inner_w = bar_x + inset, bar_w - 2 * inset
        inner_y, inner_h = y + inset, row_h - 2 * inset
        segs = _activity_segments(totals, inner_x, inner_w, inner_y, inner_h, max_hours)
        rows_svg.append(f'''
  <text x="{label_x}" y="{y + row_h - 6}" font-family="system-ui, sans-serif" font-size="13" fill="#c3c2b7">{label}</text>
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{row_h}" rx="{corner_radius}" fill="#2b2b28"/>
  <defs><clipPath id="actwk{i}"><rect x="{inner_x}" y="{inner_y}" width="{inner_w}" height="{inner_h}" rx="{corner_radius}"/></clipPath></defs>
  <g clip-path="url(#actwk{i})">{segs}</g>
  <text x="{bar_x + bar_w + 12}" y="{y + row_h - 6}" font-family="system-ui, sans-serif" font-size="13" fill="#ffffff">{_format_hm(sum(totals.values()) / 60)}</text>''')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{label_x}" y="20" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  {"".join(rows_svg)}
</svg>"""


def render_activity_legend_svg(prefixes):
    """Horizontal legend (swatch + project name) in the given order, wrapping
    past the two-chart width."""
    if not prefixes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
    pad, sw, gap, item_gap, line_h, font_px = 20, 13, 8, 24, 26, 13
    max_width = 1300
    items, x, line, right = [], pad, 0, pad
    for p in prefixes:
        item_w = sw + gap + int(len(p) * font_px * 0.62) + item_gap
        if x + item_w > max_width and x > pad:
            line += 1
            x = pad
        yy = 6 + line * line_h
        items.append(
            f'<rect x="{x}" y="{yy}" width="{sw}" height="{sw}" rx="2" fill="{project_color(p)}"/>'
            f'<text x="{x + sw + gap}" y="{yy + sw - 1}" font-family="system-ui, sans-serif" '
            f'font-size="{font_px}" fill="#c3c2b7">{p}</text>'
        )
        x += item_w
        right = max(right, x)
    width = min(max_width, right)
    height = (line + 1) * line_h + 6
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  {"".join(items)}
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
  .charts-row {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; align-items: flex-start; }}
  .charts-row img {{ max-width: 100%; }}
  /* légende alignée sous la colonne activité (largeur graphe 640 + gap 1rem) */
  #legend {{ display: block; max-width: 100%; margin: .3rem 0 1.5rem calc(640px + 1rem); }}
  @media (max-width: 1360px) {{ #legend {{ margin-left: 0; }} }}
  a {{ color: #3987e5; text-decoration: none; }}
  .nav {{ margin-bottom: 1.5rem; }}
</style>
</head>
<body>
<div id="current-box" class="empty">aucune tâche en cours</div>

<div class="charts-row">
  <img id="billable" src="{billable_url}" alt="heures facturables">
  <img id="day-activity" src="{activity_url}" alt="activité du jour par projet">
</div>

<div class="charts-row">
  <img id="week" src="{week_url}" alt="heures facturables par jour de la semaine">
  <img id="week-activity" src="{activity_week_url}" alt="activité de la semaine par projet">
</div>

<img id="legend" src="{legend_url}" alt="légende des projets">

<p class="nav"><a href="{weeks_url}">→ semaines facturables</a></p>

<h1>pomofocus_webhook.csv — semaine courante, mis à jour toutes les 3s (plus récent en haut)</h1>
<table>
  <thead><tr><th>Date</th><th>Projet</th><th>Tâche</th><th>Min</th><th>Début</th><th>Fin</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="status">chargement...</div>
<script>
const API_URL = "{api_url}";
const BILLABLE_URL = "{billable_url}";
const WEEK_URL = "{week_url}";
const ACTIVITY_URL = "{activity_url}";
const ACTIVITY_WEEK_URL = "{activity_week_url}";
const LEGEND_URL = "{legend_url}";
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
  document.getElementById("week").src = WEEK_URL + "?t=" + Date.now();
  document.getElementById("day-activity").src = ACTIVITY_URL + "?t=" + Date.now();
  document.getElementById("week-activity").src = ACTIVITY_WEEK_URL + "?t=" + Date.now();
  document.getElementById("legend").src = LEGEND_URL + "?t=" + Date.now();
}}

poll();
setInterval(poll, 3000);
</script>
</body>
</html>
"""


WEEKS_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Semaines facturables</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee; }}
  h1 {{ font-size: 1.1rem; font-weight: normal; color: #999; }}
  a {{ color: #3987e5; text-decoration: none; }}
  .week {{ margin-bottom: 1.8rem; }}
  .week-label {{ font-size: .8rem; text-transform: uppercase; color: #999; margin: 0 0 .4rem; }}
  .week svg {{ display: block; max-width: 100%; }}
</style>
</head>
<body>
<h1><a href="{view_url}">← live</a> — {count} semaines facturables les plus récentes</h1>
{blocks}
</body>
</html>
"""


@app.get("/view", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/view")
def view(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    return VIEW_HTML.format(
        api_url=f"{prefix}/api/rows",
        billable_url=f"{prefix}/billable.svg",
        week_url=f"{prefix}/billable-week.svg",
        activity_url=f"{prefix}/activity.svg",
        activity_week_url=f"{prefix}/activity-week.svg",
        legend_url=f"{prefix}/activity-legend.svg",
        weeks_url=f"{prefix}/weeks",
    )


@app.get("/weeks", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/weeks")
def weeks(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    blocks = []
    for monday, sunday, day_hours in recent_billable_weeks():
        svg = render_week_svg(day_hours)
        blocks.append(
            f'<section class="week"><p class="week-label">'
            f'{_fr_week_range(monday, sunday)}</p>{svg}</section>'
        )
    return WEEKS_HTML.format(
        view_url=f"{prefix}/view",
        count=BILLABLE_WEEKS_SHOWN,
        blocks="\n".join(blocks),
    )


@app.get("/billable.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/billable.svg")
def billable_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    svg = render_billable_svg(billable_hours())
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/billable-week.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/billable-week.svg")
def billable_week_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    svg = render_week_svg(billable_hours_for_week())
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/activity.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/activity.svg")
def activity_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    today = datetime.now().strftime("%Y%m%d")
    totals = activity_by_project(_read_csv_rows(CSV_PATH), today)
    svg = render_activity_svg(totals)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/activity-week.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/activity-week.svg")
def activity_week_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    rows = _read_csv_rows(CSV_PATH)
    today = datetime.now().date()
    monday, _ = current_week_bounds(today)
    days, day = [], today
    while day >= monday:
        totals = activity_by_project(rows, day.strftime("%Y%m%d"))
        days.append((_FR_WEEKDAYS[day.weekday()], totals))
        day -= timedelta(days=1)
    svg = render_activity_week_svg(days)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/activity-legend.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/activity-legend.svg")
def activity_legend_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    rows = _read_csv_rows(CSV_PATH)
    today = datetime.now().date()
    monday, _ = current_week_bounds(today)
    week_start, week_end = monday.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    prefixes = set()
    for r in rows:
        if week_start <= r["date"] <= week_end:
            prefix = _project_prefix(r.get("project"))
            if prefix and prefix != "nan":
                prefixes.add(prefix)
    svg = render_activity_legend_svg(_ordered_projects(prefixes))
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/rows", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/api/rows")
def api_rows(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    monday, sunday = current_week_bounds()
    week_start, week_end = monday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")
    rows = [r for r in _read_csv_rows(CSV_PATH) if week_start <= r["date"] <= week_end]
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
