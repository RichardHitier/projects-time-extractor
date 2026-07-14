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
import html
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import Flask, Response, jsonify, redirect, request

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
APP_VERSION = "0.8.0"  # affiché en pied de page (miroir de pyproject.toml)

BILLABLE_PROJECTS = {p.lower() for p in _config.get("BILLABLE_PROJECTS", [])}
BILLABLE_MAX_HOURS = 4
BILLABLE_WEEKS_SHOWN = 12  # /weeks : nombre de semaines les plus récentes affichées

# /months : une ligne par semaine, N semaines par page (?n=), pagination par ?p=.
# 200 semaines de recul maximum : les données commencent en sept. 2022, soit 201
# semaines avant juillet 2026 — la page p=3 (n=60) les atteint.
MONTH_WEEKS_SHOWN, MONTH_MIN_WEEKS, MONTH_MAX_WEEKS = 60, 2, 200

_FR_WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]

# Chevrons SVG pour la navigation prev/next (couleur héritée via currentColor).
_CHEVRON_LEFT = (
    '<svg viewBox="0 0 8 12" width="10" height="13" aria-hidden="true">'
    '<path d="M6 1 1 6l5 5" fill="none" stroke="currentColor" stroke-width="1.7"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_CHEVRON_RIGHT = (
    '<svg viewBox="0 0 8 12" width="10" height="13" aria-hidden="true">'
    '<path d="M2 1 7 6l-5 5" fill="none" stroke="currentColor" stroke-width="1.7"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

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


class RowEditError(Exception):
    """Édition refusée : ligne introuvable ou horaires invalides."""


def update_csv_row(key, project, task, start, end, csv_path=None):
    """Remplace la ligne repérée par `key` (date, startTime, project, task —
    les valeurs d'AVANT l'édition, le CSV n'ayant pas d'identifiant) par les
    nouvelles valeurs. `minutes` est recalculé depuis start/end, jamais saisi.
    Lève RowEditError sans rien écrire si la ligne n'existe pas ou si les
    horaires sont invalides."""
    if csv_path is None:
        csv_path = CSV_PATH

    start_h = _hhmm_to_hours(start)
    end_h = _hhmm_to_hours(end)
    if start_h is None or end_h is None:
        raise RowEditError("horaires invalides (format attendu HH:MM)")
    if end_h <= start_h:
        raise RowEditError("la fin doit être après le début")

    rows = _read_csv_rows(csv_path)
    for index, existing in enumerate(rows):
        existing_key = (
            existing["date"],
            existing["startTime"],
            existing["project"],
            existing["task"],
        )
        if existing_key == tuple(key):
            rows[index] = {
                "date": existing["date"],
                "project": project,
                "task": task,
                "minutes": round((end_h - start_h) * 60),
                "startTime": start,
                "endTime": end,
            }
            _write_csv_rows(merge_contiguous_sessions(rows), csv_path)
            return rows[index]

    raise RowEditError("ligne introuvable (modifiée entre-temps ?)")


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


def billable_minutes(rows, day, quantize=False):
    """Billable minutes for `day`. When `quantize`, reproduces the ODS export
    rounding (`timer report --view ods`): group rows by (project, task), then
    ceil each group up to the next quarter-hour (15 min) before summing. Without
    it, returns the raw sum (grouping is transparent then)."""
    by_task = {}
    for row in rows:
        if row.get("date") != day:
            continue
        if not _row_is_billable(row):
            continue
        key = (row.get("project"), row.get("task"))
        by_task[key] = by_task.get(key, 0) + int(row.get("minutes") or 0)
    if quantize:
        return sum(-(-m // 15) * 15 for m in by_task.values())
    return sum(by_task.values())


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


def week_anchor(weeks_back, today=None):
    """Last day to display for a /live shifted `weeks_back` weeks into the past.
    The current week (0) ends at `today`; a past week ends on its Sunday."""
    if today is None:
        today = datetime.now().date()
    if weeks_back <= 0:
        return today
    monday, _ = current_week_bounds(today)
    monday -= timedelta(weeks=weeks_back)
    return monday + timedelta(days=6)


def day_label(day):
    """« Vendredi 25/07 » — étiquette de ligne des graphes de semaine. Sert aussi
    de clé de surlignage du jour courant (`highlight_label`) : les deux doivent
    se calculer ici, sinon le cadre jaune ne trouve plus sa ligne."""
    return f"{_FR_WEEKDAYS[day.weekday()]} {day.strftime('%d/%m')}"


def billable_hours_for_days(monday, last_day, rows, quantize=False):
    """Billable hours per day from `last_day` down to `monday` (most recent
    first), as (day_label, hours) pairs."""
    days = []
    day = last_day
    while day >= monday:
        hours = billable_minutes(rows, day.strftime("%Y%m%d"), quantize=quantize) / 60
        days.append((day_label(day), hours))
        day -= timedelta(days=1)
    return days


def billable_hours_for_week(today=None):
    """Billable hours per elapsed day of the current week (Monday..today),
    most recent first, as (day_label, hours) pairs."""
    if today is None:
        today = datetime.now().date()
    monday, _ = current_week_bounds(today)
    return billable_hours_for_days(monday, today, _read_csv_rows(CSV_PATH))


def recent_weeks(today=None, count=BILLABLE_WEEKS_SHOWN, page=0, quantize=False):
    """The `count` most recent weeks, most recent first, as
    (monday, sunday, billable_days, activity_days) tuples — billable hours and
    per-project activity per day, most recent first. The current week stops at
    `today`; completed weeks span Monday..Sunday. Empty weeks are kept.

    `page` shifts the window `page * count` weeks into the past: page 0 is the
    most recent window (current week ending at `today`); pages > 0 are older and
    span complete Monday..Sunday weeks."""
    if today is None:
        today = datetime.now().date()
    rows = _read_csv_rows(CSV_PATH)
    monday, _ = current_week_bounds(today)
    if page > 0:
        monday -= timedelta(weeks=page * count)
        last_day = monday + timedelta(days=6)
    else:
        last_day = today
    weeks = []
    for _ in range(count):
        sunday = monday + timedelta(days=6)
        billable, activity, day = [], [], last_day
        while day >= monday:
            key, label = day.strftime("%Y%m%d"), day_label(day)
            billable.append((label, billable_minutes(rows, key, quantize=quantize) / 60))
            activity.append((label, activity_by_project(rows, key)))
            day -= timedelta(days=1)
        weeks.append((monday, sunday, billable, activity))
        monday -= timedelta(days=7)
        last_day = monday + timedelta(days=6)  # semaine précédente : dimanche
    return weeks


def recent_week_totals(today=None, n=MONTH_WEEKS_SHOWN, page=0, quantize=False):
    """The `n` most recent weeks, most recent first, as
    (monday, sunday, label, billable_hours, {prefix: minutes}) tuples — one row
    per week instead of one per day (/months). The current week stops at `today`;
    completed weeks span Monday..Sunday. Empty weeks are kept.

    `page` recule la fenêtre de `page * n` semaines, comme recent_weeks : page 0
    est la fenêtre courante, les suivantes sont plus anciennes (et complètes,
    leur dimanche étant passé)."""
    if today is None:
        today = datetime.now().date()
    rows = _read_csv_rows(CSV_PATH)
    monday, _ = current_week_bounds(today)
    monday -= timedelta(weeks=page * n)
    weeks = []
    for _ in range(n):
        sunday = monday + timedelta(days=6)
        last_day = min(sunday, today)
        minutes, activity, day = 0, {}, monday
        while day <= last_day:
            key = day.strftime("%Y%m%d")
            minutes += billable_minutes(rows, key, quantize=quantize)
            for prefix, mins in activity_by_project(rows, key).items():
                activity[prefix] = activity.get(prefix, 0) + mins
            day += timedelta(days=1)
        label = f"S{monday.isocalendar()[1]:02d}"
        weeks.append((monday, sunday, label, minutes / 60, activity))
        monday -= timedelta(days=7)
    return weeks


def _fr_window(weeks):
    """« février 2023 → mars 2024 » — la période couverte par une fenêtre de
    /months (weeks est trié du plus récent au plus ancien)."""
    if not weeks:
        return ""
    debut = weeks[-1][0]
    fin = weeks[0][1]
    return (f"{_FR_MONTHS[debut.month - 1]} {debut.year}"
            f" → {_FR_MONTHS[fin.month - 1]} {fin.year}")


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

# Colonne des heures (chiffres à droite des barres) : alignée à droite sur cette
# abscisse, la même dans les deux graphes de semaine (largeur 640, marge 20) —
# c'est ce qui les fait s'aligner entre eux quand ils sont côte à côte.
WEEK_HOURS_RIGHT_X = 620

# Les barres finissent toutes ici ; c'est leur DÉBUT qui s'adapte à la longueur
# des étiquettes (« Vendredi 25/07 » sur /live et /weeks, « S28 » sur /months).
# Le repère de fin, la zone de débordement et la colonne d'heures restent donc
# fixes d'une page à l'autre — seule la largeur utile de la barre varie.
WEEK_BAR_END_X = 490
WEEK_BAR_MIN_X = 110  # début de barre historique, plancher pour les labels courts


def _bar_start_x(labels):
    """Abscisse de début des barres : après la plus large étiquette."""
    widest = max((_text_width(label) for label in labels), default=0)
    return max(WEEK_BAR_MIN_X, 20 + round(widest) + 12)


def _week_header_bar(total_hours, max_hours, value_x, bar_end_x=None, label_x=20, y=4, height=34, divisions=4, overflow_max=0):
    """Full-width progress bar used as the header of a week chart, in place of a
    text title. The grey fill is clamped to the bar; a total past `max_hours`
    spills into a gold overflow lane of width `overflow_max` to the right of the
    bar (same as the day rows), when `overflow_max` > 0. The `nn / Nh` figure is
    right-anchored at `value_x` to line up with the day-row figures below. The
    bar's right edge is `bar_end_x` (default: just left of the figure) so it can
    be aligned with the day-row bars rather than reaching the figures column."""
    bar_x = label_x
    if bar_end_x is None:
        bar_end_x = value_x - 12
    bar_w = bar_end_x - bar_x
    ratio = max(0, total_hours / max_hours) if max_hours else 0
    fill_w = (bar_w - 6) * min(ratio, 1)
    corner_radius = 5
    fill_rect = ""
    if fill_w > 0:
        fill_rect = (
            f'<rect x="{bar_x + 3}" y="{y + 3}" width="{fill_w:.1f}" '
            f'height="{height - 6}" rx="{corner_radius}" fill="#9d9d93"/>'
        )
    overflow_rect = ""
    if overflow_max and ratio > 1:
        overflow_w = overflow_max * min(ratio - 1, 1)
        overflow_rect = (
            f'<rect x="{bar_end_x + 3}" y="{y + 3}" width="{overflow_w:.1f}" '
            f'height="{height - 6}" rx="{corner_radius}" fill="#d9a441"/>'
        )
    # `divisions` intervalles égaux : traits internes séparant les graduations
    # (5 intervalles → tous les 4h sur /20h ; tous les 8h sur /40h)
    ticks = "".join(
        f'<line x1="{bar_x + bar_w * i / divisions:.1f}" y1="{y - 4}" '
        f'x2="{bar_x + bar_w * i / divisions:.1f}" y2="{y + height + 4}" '
        f'stroke="#383835" stroke-width="1" opacity=".6"/>'
        for i in range(1, divisions)
    )
    return f'''
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{height}" rx="{corner_radius}" fill="#2e2e2b"/>
  {fill_rect}
  {overflow_rect}
  {ticks}
  <text x="{value_x}" y="{y + height // 2 + 5}" text-anchor="end" font-family="system-ui, sans-serif" font-size="14" font-weight="700" fill="#ffffff">{_format_hm(total_hours)} / {max_hours}h</text>'''


def _text_width(s, size=13):
    """Rough proportional text width (system-ui) for sizing highlight frames."""
    narrow = set("iIjl.,:;'!| ")
    return sum(size * (0.30 if c in narrow else 0.60) for c in s)


# Début de barre des graphes à étiquettes de jour (/live, /weeks). Calculé une
# fois sur l'étiquette la plus large possible, et non sur les lignes réellement
# affichées : la semaine courante n'a que les jours écoulés (« Lundi 13/07 »
# seul, le lundi), et une barre qui démarrerait plus à gauche que celle des
# semaines complètes les désalignerait sur /weeks.
DAY_BAR_START_X = _bar_start_x(f"{name} 00/00" for name in _FR_WEEKDAYS) + 12


def _split_day_label(label):
    """('Vendredi', '25/07') — nom et date d'une étiquette de jour. La date est
    vide pour les étiquettes sans date (« S28 » sur /months)."""
    name, _, tail = label.rpartition(" ")
    if name and len(tail) == 5 and tail[2] == "/" and tail.replace("/", "").isdigit():
        return name, tail
    return label, ""


def _row_label_svg(label, label_x, bar_x, baseline_y, fill="#c3c2b7"):
    """Nom du jour aligné à gauche, date alignée à droite contre la barre."""
    name, date = _split_day_label(label)
    font = 'font-family="system-ui, sans-serif" font-size="13"'
    svg = f'<text x="{label_x}" y="{baseline_y}" {font} fill="{fill}">{name}</text>'
    if date:
        svg += (
            f'<text x="{bar_x - 12}" y="{baseline_y}" text-anchor="end" {font} '
            f'fill="{fill}">{date}</text>'
        )
    return svg


def _label_frame_w(label, label_x, bar_x):
    """Largeur du cadre de surlignage : toute la colonne d'étiquettes quand elle
    porte une date (nom à gauche + date à droite), sinon le texte seul."""
    _, date = _split_day_label(label)
    return (bar_x - 12 - label_x) if date else _text_width(label)


def month_row_groups(mondays):
    """[(première_ligne, dernière_ligne, 'Juillet', '26')] — lignes consécutives
    dont le lundi tombe dans le même mois. Une semaine à cheval sur deux mois est
    rattachée au mois de son lundi. L'année est portée séparément : elle survit à
    l'abréviation du nom (« Sep.25 »), et /months affiche jusqu'à 120 semaines,
    où deux « Juillet » d'années différentes se côtoient."""
    groups = []
    previous = None
    for i, monday in enumerate(mondays):
        key = (monday.year, monday.month)
        if groups and key == previous:
            first, _, name, year = groups[-1]
            groups[-1] = (first, i, name, year)
        else:
            groups.append((
                i, i,
                _FR_MONTHS[monday.month - 1].capitalize(),
                monday.strftime("%y"),
            ))
        previous = key
    return groups


# Étiquette de mois de /months (texte vertical dans la gouttière). Modifiables
# à chaud : le conteneur monte le dossier, un simple rechargement suffit.
MONTH_LABEL_SIZE = 15
MONTH_LABEL_GAP = 26  # écart entre le texte du mois et la barre
MONTH_LABEL_WEIGHT = "normal"  # "normal" pour dégraisser
MONTH_LABEL_COLOR = "#ffffff"  # étiquettes de semaine voisines : #c3c2b7


CHART_TITLE_H = 26  # bandeau du titre visible, au-dessus de la barre d'en-tête
CHART_TITLE_SIZE = 13
CHART_TITLE_WEIGHT = "700"
CHART_TITLE_COLOR = "#ffffff"


def _chart_title_svg(title, x=320, y=18):
    """Titre visible du graphe, centré sur sa largeur (640 px). Il vit DANS le
    SVG et non dans la page : sur /live les graphes sont des <img>, la page HTML
    ignore donc les totaux."""
    return (
        f'<text x="{x}" y="{y}" text-anchor="middle" '
        f'font-family="system-ui, sans-serif" '
        f'font-size="{CHART_TITLE_SIZE}" font-weight="{CHART_TITLE_WEIGHT}" '
        f'letter-spacing="0.5" fill="{CHART_TITLE_COLOR}">{title}</text>'
    )


def _month_labels_svg(groups, top, row_h, row_gap, x):
    """« Juillet26 » écrit verticalement (lu de bas en haut) dans la gouttière
    entre les étiquettes de semaine et les barres, centré sur les lignes du
    mois. Un nom long (Septembre…) est abrégé quand l'étiquette déborde du bloc
    de lignes — l'année est conservée (« Sep.25 ») ; les noms courts (Mai, Juin,
    Août) restent entiers, les abréger les rallongerait."""
    pitch = row_h + row_gap
    labels = []
    for first, last, name, year in groups:
        y0 = top + first * pitch
        y1 = top + last * pitch + row_h
        span = y1 - y0
        text = f"{name} {year}"
        if len(name) > 4 and _text_width(text, MONTH_LABEL_SIZE) > span:
            text = f"{name[:3]}. {year}"
        labels.append(
            f'<text transform="translate({x},{(y0 + y1) / 2:.1f}) rotate(-90)" '
            f'text-anchor="middle" font-family="system-ui, sans-serif" '
            f'font-size="{MONTH_LABEL_SIZE}" font-weight="{MONTH_LABEL_WEIGHT}" '
            f'fill="{MONTH_LABEL_COLOR}">{text}</text>'
        )
    return "".join(labels)


def _hl_frame(x, y, w, h, rx=4):
    """Yellow outline used to flag the current day's label/hours/bar."""
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="none" stroke="#ffd43b" stroke-width="1.5"/>')


def _hatch_pattern(pattern_id, color):
    """Diagonal-line hatch (45°) in `color` on a faint tint of itself. Fills the
    running task's elapsed-time zone so it reads as "in progress", distinct from
    the solid recorded fill."""
    return (
        f'<pattern id="{pattern_id}" patternUnits="userSpaceOnUse" width="6" '
        f'height="6" patternTransform="rotate(45)">'
        f'<rect width="6" height="6" fill="{color}" opacity="0.16"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{color}" stroke-width="2.4"/>'
        f'</pattern>'
    )


_BILLABLE_HATCH_ID = "hatch-billable"


def render_week_svg(day_hours, max_hours=BILLABLE_MAX_HOURS, week_max_hours=BILLABLE_WEEK_MAX_HOURS, highlight_label=None, current_hours=0.0, title_label="SEMAINE", show_header=True, month_groups=None, bar_start=None, show_title=True, title_totals=True):
    """Render a "SEMAINE : total / Nh" header, then one bar per
    (day_label, hours) pair, most recent first. `show_header=False` drops the
    total header bar (and its vertical space) — /months shows weeks, whose total
    over N weeks says little.

    `month_groups` (cf. month_row_groups) writes the month name vertically in the
    gutter between the row labels and the bars — /months only.

    Bars past `max_hours` overflow past a boundary marker (in a distinct
    color) instead of being clamped, up to a capped overflow lane.

    `current_hours` (> 0 only for the running billable task, week w==0) draws a
    grey hatched zone after the solid fill on the `highlight_label` row, clamped
    within the bar.

    Rows are labelled, not dated: /months passes weeks rather than days, hence
    `title_label` for the SVG tooltip.
    """
    width = 640
    row_h, row_gap = 22, 12
    header_h = 38 if show_header else 0
    title_h = CHART_TITLE_H if show_title else 0
    top = title_h + header_h + row_gap
    label_x, overflow_max = 20, 60
    bar_x = bar_start or _bar_start_x(label for label, _ in day_hours)
    bar_w = WEEK_BAR_END_X - bar_x
    corner_radius = 5
    inset = 3
    height = top + len(day_hours) * (row_h + row_gap)
    total_hours = sum(hours for _, hours in day_hours)
    title = f"{title_label} : {_format_hm(total_hours)} / {week_max_hours}h"

    hatch_defs = ""
    rows_svg = []
    for i, (label, hours) in enumerate(day_hours):
        y = top + i * (row_h + row_gap)
        ratio = hours / max_hours if max_hours else 0
        inner_h = row_h - 2 * inset
        inner_w = bar_w - 2 * inset
        fill_w = inner_w * min(ratio, 1)
        fill_rect = ""
        if fill_w > 0:
            fill_rect = (
                f'<rect x="{bar_x + inset}" y="{y + inset}" width="{fill_w:.1f}" '
                f'height="{inner_h}" rx="{corner_radius}" fill="#9d9d93"/>'
            )
        hatch_rect = ""
        if current_hours > 0 and label == highlight_label:
            hatch_w = min(inner_w * (current_hours / max_hours), inner_w - fill_w)
            if hatch_w > 0:
                hatch_defs = f'<defs>{_hatch_pattern(_BILLABLE_HATCH_ID, "#9d9d93")}</defs>'
                hatch_rect = (
                    f'<rect x="{bar_x + inset + fill_w:.1f}" y="{y + inset}" '
                    f'width="{hatch_w:.1f}" height="{inner_h}" '
                    f'fill="url(#{_BILLABLE_HATCH_ID})"/>'
                )
        overflow_rect = ""
        if ratio > 1:
            overflow_w = overflow_max * min(ratio - 1, 1)
            overflow_rect = (
                f'<rect x="{bar_x + bar_w + inset}" y="{y + inset}" width="{overflow_w:.1f}" '
                f'height="{inner_h}" rx="{corner_radius}" fill="#d9a441"/>'
            )
        hours_text = _format_hm(hours)
        hours_w = _text_width(hours_text)
        frames = ""
        if label == highlight_label:
            frames = (
                _hl_frame(label_x - 5, y, _label_frame_w(label, label_x, bar_x) + 10, row_h)
                + _hl_frame(WEEK_HOURS_RIGHT_X - hours_w - 5, y, hours_w + 10, row_h)
            )
        rows_svg.append(f'''
  {_row_label_svg(label, label_x, bar_x, y + row_h - 6)}
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{row_h}" rx="{corner_radius}" fill="#2e2e2b"/>
  {fill_rect}
  {hatch_rect}
  <line x1="{bar_x + bar_w}" y1="{y - 2}" x2="{bar_x + bar_w}" y2="{y + row_h + 2}" stroke="#c3c2b7" stroke-width="2"/>
  {overflow_rect}
  {frames}
  <text x="{WEEK_HOURS_RIGHT_X}" y="{y + row_h - 6}" text-anchor="end" font-family="system-ui, sans-serif" font-size="13" fill="#ffffff">{hours_text}</text>''')

    header_bar = ""
    if show_header:
        header_bar = _week_header_bar(
            total_hours, week_max_hours, WEEK_HOURS_RIGHT_X,
            bar_end_x=bar_x + bar_w, divisions=5, overflow_max=overflow_max,
            y=title_h + 4,
        )
    month_labels = ""
    if month_groups:
        month_labels = _month_labels_svg(
            month_groups, top, row_h, row_gap, bar_x - MONTH_LABEL_GAP
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  {_chart_title_svg(title if title_totals else title_label) if show_title else ''}
  {hatch_defs}
  {header_bar}
  {month_labels}
  {"".join(rows_svg)}
</svg>"""


# ── Activité par projet (couleurs identiques à `timer day-bars`) ──────────────
ACTIVITY_MAX_HOURS = 8
ACTIVITY_WEEK_MAX_HOURS = 40

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


def activity_week_days(rows, last_day):
    """(day_label, {project: minutes}) per day from `last_day` down to its
    week's Monday, most recent first."""
    monday, _ = current_week_bounds(last_day)
    days, day = [], last_day
    while day >= monday:
        totals = activity_by_project(rows, day.strftime("%Y%m%d"))
        days.append((day_label(day), totals))
        day -= timedelta(days=1)
    return days


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
    return "".join(segs), x - x0  # segments + largeur réellement remplie


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
    segs, fill_w = _activity_segments(totals, inner_x, inner_w, inner_y, inner_h, max_hours)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <defs><clipPath id="actbar"><rect x="{inner_x}" y="{inner_y}" width="{fill_w:.1f}" height="{inner_h}" rx="{corner_radius}"/></clipPath></defs>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{bar_x}" y="30" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{corner_radius}" fill="#2b2b28"/>
  <g clip-path="url(#actbar)">{segs}</g>
  {ticks}
</svg>"""


def render_activity_week_svg(days, max_hours=ACTIVITY_MAX_HOURS, uid="", highlight_label=None, week_max_hours=ACTIVITY_WEEK_MAX_HOURS, current_hours=0.0, current_prefix=None, title_label="ACTIVITÉ SEMAINE", show_header=True, month_groups=None, bar_start=None, show_title=True, title_totals=True):
    """One stacked activity bar per day (most recent first). Row geometry
    matches render_week_svg so the two week charts line up side by side —
    including `show_header` and `month_groups`, to be set the same way on both.

    `uid` disambiguates the clipPath ids: several of these SVGs are inlined in
    one HTML document (the /weeks page), where clipPath ids are document-global,
    so a shared `actwk{i}` would make every week clip to the first week's bar.

    `current_hours`/`current_prefix` (set only for the running task, week w==0)
    draw a hatched zone in the project's color after the stacked segments on the
    `highlight_label` row, clamped within the bar.

    Rows are labelled, not dated: /months passes weeks rather than days, hence
    `title_label` for the SVG tooltip."""
    width = 640
    row_h, row_gap = 22, 12
    header_h = 38 if show_header else 0
    title_h = CHART_TITLE_H if show_title else 0
    top = title_h + header_h + row_gap
    label_x = 20
    bar_x = bar_start or _bar_start_x(label for label, _ in days)
    bar_w = WEEK_BAR_END_X - bar_x
    corner_radius, inset = 5, 3
    height = top + len(days) * (row_h + row_gap)
    week_total = sum(sum(t.values()) for _, t in days) / 60
    title = f"{title_label} : {_format_hm(week_total)} / {week_max_hours}h"
    hatch_defs = ""
    rows_svg = []
    for i, (label, totals) in enumerate(days):
        y = top + i * (row_h + row_gap)
        inner_x, inner_w = bar_x + inset, bar_w - 2 * inset
        inner_y, inner_h = y + inset, row_h - 2 * inset
        segs, fill_w = _activity_segments(totals, inner_x, inner_w, inner_y, inner_h, max_hours)
        hatch_rect = ""
        if current_hours > 0 and current_prefix and label == highlight_label:
            hatch_w = min(inner_w * (current_hours / max_hours), inner_w - fill_w)
            if hatch_w > 0:
                hid = f"acthatch{uid}"
                hatch_defs = f'<defs>{_hatch_pattern(hid, project_color(current_prefix))}</defs>'
                hatch_rect = (
                    f'<rect x="{inner_x + fill_w:.1f}" y="{inner_y}" '
                    f'width="{hatch_w:.1f}" height="{inner_h}" fill="url(#{hid})"/>'
                )
        hours_text = _format_hm(sum(totals.values()) / 60)
        hours_w = _text_width(hours_text)
        frames = ""
        if label == highlight_label:
            frames = (
                _hl_frame(label_x - 5, y, _label_frame_w(label, label_x, bar_x) + 10, row_h)
                + _hl_frame(WEEK_HOURS_RIGHT_X - hours_w - 5, y, hours_w + 10, row_h)
            )
        rows_svg.append(f'''
  {_row_label_svg(label, label_x, bar_x, y + row_h - 6)}
  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{row_h}" rx="{corner_radius}" fill="#2b2b28"/>
  <defs><clipPath id="actwk{uid}{i}"><rect x="{inner_x}" y="{inner_y}" width="{fill_w:.1f}" height="{inner_h}" rx="{corner_radius}"/></clipPath></defs>
  <g clip-path="url(#actwk{uid}{i})">{segs}</g>
  {hatch_rect}
  {frames}
  <text x="{WEEK_HOURS_RIGHT_X}" y="{y + row_h - 6}" text-anchor="end" font-family="system-ui, sans-serif" font-size="13" fill="#ffffff">{hours_text}</text>''')
    header_bar = ""
    if show_header:
        header_bar = _week_header_bar(
            week_total, week_max_hours, WEEK_HOURS_RIGHT_X,
            bar_end_x=bar_x + bar_w, divisions=5, y=title_h + 4,
        )
    month_labels = ""
    if month_groups:
        month_labels = _month_labels_svg(
            month_groups, top, row_h, row_gap, bar_x - MONTH_LABEL_GAP
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  {_chart_title_svg(title if title_totals else title_label) if show_title else ''}
  {hatch_defs}
  {header_bar}
  {month_labels}
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


ROWS_SHOWN = 50  # /rows : nb de lignes affichées par défaut (surchargé par ?n=N)
ROWS_MAX = 500

SWIMLANE_DAYS = 10  # nb de jours par défaut (surchargé par ?d=N)
SWIMLANE_MIN_DAYS, SWIMLANE_MAX_DAYS = 1, 60  # bornes du sélecteur −1/+1
SWIMLANE_HOUR_MIN, SWIMLANE_HOUR_MAX = 6, 24


def _hhmm_to_hours(value):
    """'HH:MM' -> decimal hours of day, or None if unparseable."""
    try:
        h, m = value.split(":")
        return int(h) + int(m) / 60
    except (ValueError, AttributeError):
        return None


def swimlane_days(rows, last_day, n=SWIMLANE_DAYS):
    """`n` days ending at `last_day`, most recent first. Each entry is
    (label, is_weekend, sessions) with sessions a list of
    (start_h, end_h, minutes, prefix) in decimal hours of the day. Days with no
    activity keep an empty session list (blank row, cf. critère 2)."""
    by_date = {}
    for row in rows:
        by_date.setdefault(row.get("date"), []).append(row)
    days = []
    for i in range(n):
        day = last_day - timedelta(days=i)
        sessions = []
        for row in by_date.get(day.strftime("%Y%m%d"), []):
            prefix = _project_prefix(row.get("project"))
            if not prefix or prefix == "nan":
                continue
            start_h = _hhmm_to_hours(row.get("startTime"))
            end_h = _hhmm_to_hours(row.get("endTime"))
            if start_h is None or end_h is None:
                continue
            minutes = int(row.get("minutes") or 0)
            if end_h <= start_h:  # passage minuit / trame courte, cf. core.plots
                end_h = start_h + minutes / 60
            sessions.append((start_h, end_h, minutes, prefix))
        label = f"{_FR_WEEKDAYS[day.weekday()][:3].lower()}. {day.strftime('%d/%m')}"
        days.append((label, day.weekday() >= 5, sessions))
    return days


def render_swimlane_svg(days):
    """Gantt-style swimlane: one row per day (most recent first), colored bars
    positioned by hour of day (6h→24h), same dark theme as the activity charts.
    Reuses project_color so colors match /activity."""
    width = 960
    label_x, bar_x, bar_w = 20, 100, 840
    hmin, hmax = SWIMLANE_HOUR_MIN, SWIMLANE_HOUR_MAX
    span = hmax - hmin
    row_h, row_gap, top = 24, 6, 60
    height = top + len(days) * (row_h + row_gap) + 10

    def hx(h):
        h = max(hmin, min(h, hmax))
        return bar_x + (h - hmin) / span * bar_w

    tracks, bars = [], []
    for i, (label, is_we, sessions) in enumerate(days):
        y = top + i * (row_h + row_gap)
        track_fill = "#201f1d" if is_we else "#2b2b28"
        label_fill = "#6f6e66" if is_we else "#c3c2b7"
        tracks.append(
            f'<rect x="{bar_x}" y="{y}" width="{bar_w}" height="{row_h}" rx="4" fill="{track_fill}"/>'
        )
        tracks.append(
            f'<text x="{label_x}" y="{y + row_h - 7}" font-family="monospace" '
            f'font-size="12" fill="{label_fill}">{label}</text>'
        )
        for start_h, end_h, minutes, prefix in sessions:
            x0, x1 = hx(start_h), hx(end_h)
            if x1 - x0 < 0.5:
                continue
            bars.append(
                f'<rect x="{x0:.1f}" y="{y + 3}" width="{x1 - x0:.1f}" '
                f'height="{row_h - 6}" rx="2" fill="{project_color(prefix)}"/>'
            )
            if x1 - x0 > 24:  # ~30 min : assez large pour un label lisible
                bars.append(
                    f'<text x="{(x0 + x1) / 2:.1f}" y="{y + row_h - 8}" '
                    f'text-anchor="middle" font-family="system-ui, sans-serif" '
                    f'font-size="9" fill="#ffffff" font-weight="bold">{minutes}m</text>'
                )

    grid = []
    for h in range(hmin, hmax + 1, 2):
        gx = bar_x + (h - hmin) / span * bar_w
        grid.append(
            f'<line x1="{gx:.1f}" y1="{top - 6}" x2="{gx:.1f}" y2="{height - 8}" '
            f'stroke="#383835" stroke-width="1" stroke-dasharray="2 3" opacity=".6"/>'
        )
        grid.append(
            f'<text x="{gx:.1f}" y="{top - 12}" text-anchor="middle" '
            f'font-family="system-ui, sans-serif" font-size="11" fill="#7a7a72">{h:02d}h</text>'
        )

    title = f"SWIMLANE · {len(days)} DERNIERS JOURS"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{title}</title>
  <rect width="{width}" height="{height}" fill="#1a1a19"/>
  <text x="{label_x}" y="30" font-family="system-ui, sans-serif" font-size="18" fill="#ffffff">{title}</text>
  {"".join(tracks)}
  {"".join(grid)}
  {"".join(bars)}
</svg>"""


def _menu_bar(prefix, active):
    """Shared top navigation across /live, /weeks, /months, /swimlane and /rows.
    `active` is one of 'live' | 'weeks' | 'month' | 'swimlane' | 'rows' and gets
    the highlighted pill."""
    items = [
        ("live", "Live", f"{prefix}/live"),
        ("weeks", "Semaines", f"{prefix}/weeks"),
        ("month", "Mois", f"{prefix}/months"),
        ("swimlane", "Swimlane", f"{prefix}/swimlane"),
        ("rows", "Lignes", f"{prefix}/rows"),
    ]
    links = "".join(
        f'<a href="{href}" class="active">{text}</a>'
        if key == active
        else f'<a href="{href}">{text}</a>'
        for key, text, href in items
    )
    return f'<nav class="menubar">{links}</nav>'


def _round_toggle_html(enabled):
    """Checkbox toggling the 1/4h billable rounding. Stores its state in a
    `round` cookie (path=/) so it carries across /live and /weeks, then reloads
    to re-render the server-side charts with the new setting."""
    checked = " checked" if enabled else ""
    return (
        '<label class="roundtoggle" title="Arrondir chaque tâche facturable au quart d\'heure supérieur (comme l\'export ODS)">'
        '<input type="checkbox"' + checked + " "
        "onchange=\"document.cookie='round='+(this.checked?1:0)+';path=/;max-age=31536000';location.reload()\">"
        " arrondi 1/4h</label>"
    )


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


LIVE_HTML = """<!doctype html>
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
    box-sizing: border-box; min-height: 5.4rem;
  }}
  #current-box.empty {{ display: flex; align-items: center; color: #666; font-style: italic;
    border-color: #9d9d93; }}
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
  .menubar {{ display: flex; gap: .6rem; margin-bottom: 1.5rem; }}
  .menubar a {{ background: #2e2e2b; padding: .4rem .9rem; border-radius: 999px;
    text-transform: uppercase; font-size: .8rem; color: #bbb; transition: background .15s ease; }}
  .menubar a:hover {{ background: #3c3c37; }}
  .menubar a.active {{ background: #3987e5; color: #fff; }}
  .weeknav {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .weeknav a {{ display: inline-flex; align-items: center; gap: .3em; background: #2e2e2b;
    padding: .4rem .8rem; border-radius: 999px; transition: background .15s ease; }}
  .weeknav a:hover {{ background: #3c3c37; }}
  .weeknav svg {{ flex: none; }}
  .weeknav .week-label {{ color: #999; text-transform: uppercase; font-size: .8rem; margin: 0 auto; }}
  .roundtoggle {{ display: inline-flex; align-items: center; gap: .4rem; color: #bbb;
    font-size: .8rem; text-transform: uppercase; margin-bottom: 1.5rem; cursor: pointer; }}
  .roundtoggle input {{ accent-color: #3987e5; cursor: pointer; }}
  .ver {{ color: #666; font-size: .7rem; margin-top: 2rem; }}
</style>
</head>
<body>
{menu}
{nav}
{round_toggle}

<div class="charts-row">
  <img id="week" src="{week_url}" alt="heures facturables par jour de la semaine">
  <img id="week-activity" src="{activity_week_url}" alt="activité de la semaine par projet">
</div>

<img id="legend" src="{legend_url}" alt="légende des projets">

{current_box}

<h1>pomofocus_webhook.csv — aujourd'hui, mis à jour toutes les 3s (plus récent en haut)</h1>
<table>
  <thead><tr><th>Date</th><th>Projet</th><th>Tâche</th><th>Min</th><th>Début</th><th>Fin</th></tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="status">chargement...</div>
<script>
const API_URL = "{api_url}";
const WEEK_URL = "{week_url}";
const ACTIVITY_WEEK_URL = "{activity_week_url}";
const LEGEND_URL = "{legend_url}";
let known = new Set();

function rowHtml(r) {{
  return `<td>${{r.date}}</td><td>${{r.project}}</td><td>${{r.task}}</td>` +
         `<td>${{r.minutes}}</td><td>${{r.startTime}}</td><td>${{r.endTime}}</td>`;
}}

function bust(url) {{ return url + (url.includes("?") ? "&" : "?") + "t=" + Date.now(); }}

function setSrc(id, url) {{
  const el = document.getElementById(id);
  if (el) el.src = bust(url);
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
  if (box) {{
    if (data.current) {{
      box.className = "";
      box.innerHTML = `<span class="dot"></span>${{data.current.project}} — ${{data.current.task}}` +
        `<table><tbody><tr>${{rowHtml(data.current)}}</tr></tbody></table>`;
    }} else {{
      box.className = "empty";
      box.textContent = "aucune tâche en cours";
    }}
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

  setSrc("week", WEEK_URL);
  setSrc("week-activity", ACTIVITY_WEEK_URL);
  setSrc("legend", LEGEND_URL);
}}

poll();
setInterval(poll, 3000);
</script>
<footer class="ver">v{version}</footer>
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
  #legend svg {{ display: block; max-width: 100%; margin: .2rem 0 1.8rem; }}
  .menubar {{ display: flex; gap: .6rem; margin-bottom: 1.5rem; }}
  .menubar a {{ background: #2e2e2b; padding: .4rem .9rem; border-radius: 999px;
    text-transform: uppercase; font-size: .8rem; color: #bbb; transition: background .15s ease; }}
  .menubar a:hover {{ background: #3c3c37; }}
  .menubar a.active {{ background: #3987e5; color: #fff; }}
  .week {{ margin-bottom: 1.8rem; }}
  .week-label {{ font-size: .8rem; text-transform: uppercase; color: #999; margin: 0 0 .4rem; }}
  .week-charts {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; }}
  .week-charts svg {{ max-width: 100%; }}
  .weeknav {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 0 0 1.2rem; }}
  .weeknav a {{ display: inline-flex; align-items: center; gap: .3em; background: #2e2e2b;
    padding: .4rem .8rem; border-radius: 999px; transition: background .15s ease; }}
  .weeknav a:hover {{ background: #3c3c37; }}
  .weeknav svg {{ flex: none; }}
  .roundtoggle {{ display: inline-flex; align-items: center; gap: .4rem; color: #bbb;
    font-size: .8rem; text-transform: uppercase; margin-bottom: 1.2rem; cursor: pointer; }}
  .roundtoggle input {{ accent-color: #3987e5; cursor: pointer; }}
  .ver {{ color: #666; font-size: .7rem; margin-top: 2rem; }}
</style>
</head>
<body>
{menu}
<h1>{count} semaines (page {page}) : facturable + activité</h1>
{nav}
{round_toggle}
<div id="legend">{legend}</div>
{blocks}
{nav}
<footer class="ver">v{version}</footer>
</body>
</html>
"""


MONTH_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{count} semaines — {window}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee; }}
  h1 {{ font-size: 1.1rem; font-weight: normal; color: #999; }}
  a {{ color: #3987e5; text-decoration: none; }}
  #legend svg {{ display: block; max-width: 100%; margin: .2rem 0 1.8rem; }}
  .menubar {{ display: flex; gap: .6rem; margin-bottom: 1.5rem; }}
  .menubar a {{ background: #2e2e2b; padding: .4rem .9rem; border-radius: 999px;
    text-transform: uppercase; font-size: .8rem; color: #bbb; transition: background .15s ease; }}
  .menubar a:hover {{ background: #3c3c37; }}
  .menubar a.active {{ background: #3987e5; color: #fff; }}
  .week-charts {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-start; }}
  .week-charts svg {{ max-width: 100%; }}
  .weeknav {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 0 0 1.2rem; }}
  .weeknav a, .weeknav .disabled {{ display: inline-flex; align-items: center; background: #2e2e2b;
    padding: .4rem .9rem; border-radius: 999px; transition: background .15s ease; }}
  .weeknav a:hover {{ background: #3c3c37; }}
  .weeknav .disabled {{ color: #555; }}
  .weeknav .week-count {{ color: #999; text-transform: uppercase; font-size: .8rem;
    background: none; padding: 0; }}
  .roundtoggle {{ display: inline-flex; align-items: center; gap: .4rem; color: #bbb;
    font-size: .8rem; text-transform: uppercase; margin-bottom: 1.2rem; cursor: pointer; }}
  .roundtoggle input {{ accent-color: #3987e5; cursor: pointer; }}
  .ver {{ color: #666; font-size: .7rem; margin-top: 2rem; }}
</style>
</head>
<body>
{menu}
<h1>{count} semaines, {window} : facturable + activité</h1>
{nav}
{round_toggle}
<div class="week-charts">{charts}</div>
<div id="legend">{legend}</div>
<footer class="ver">v{version}</footer>
</body>
</html>
"""


SWIMLANE_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Swimlane — {days} derniers jours</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee; }}
  a {{ color: #3987e5; text-decoration: none; }}
  .menubar {{ display: flex; gap: .6rem; margin-bottom: 1.5rem; }}
  .menubar a {{ background: #2e2e2b; padding: .4rem .9rem; border-radius: 999px;
    text-transform: uppercase; font-size: .8rem; color: #bbb; transition: background .15s ease; }}
  .menubar a:hover {{ background: #3c3c37; }}
  .menubar a.active {{ background: #3987e5; color: #fff; }}
  .daynav {{ display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
  .daynav a, .daynav .disabled {{ display: inline-flex; align-items: center; background: #2e2e2b;
    padding: .4rem .9rem; border-radius: 999px; transition: background .15s ease; }}
  .daynav a:hover {{ background: #3c3c37; }}
  .daynav .disabled {{ color: #555; }}
  .daynav .day-label {{ color: #999; text-transform: uppercase; font-size: .8rem; }}
  #chart svg {{ display: block; max-width: 100%; }}
  #legend svg {{ display: block; max-width: 100%; margin: .6rem 0 1.8rem; }}
  .ver {{ color: #666; font-size: .7rem; margin-top: 2rem; }}
</style>
</head>
<body>
{menu}
{nav}
<div id="chart">{chart}</div>
<div id="legend">{legend}</div>
<footer class="ver">v{version}</footer>
</body>
</html>
"""


ROWS_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Lignes — {count} dernières</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #111; color: #eee; }}
  h1 {{ font-size: 1.1rem; font-weight: normal; color: #999; }}
  a {{ color: #3987e5; text-decoration: none; }}
  .menubar {{ display: flex; gap: .6rem; margin-bottom: 1.5rem; }}
  .menubar a {{ background: #2e2e2b; padding: .4rem .9rem; border-radius: 999px;
    text-transform: uppercase; font-size: .8rem; color: #bbb; transition: background .15s ease; }}
  .menubar a:hover {{ background: #3c3c37; }}
  .menubar a.active {{ background: #3987e5; color: #fff; }}
  .flash {{ padding: .6rem .9rem; border-radius: 6px; margin-bottom: 1.2rem; font-size: .85rem; }}
  .flash.ok {{ background: #1d3a25; color: #7ddb9b; }}
  .flash.err {{ background: #3d2020; color: #e58787; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ text-align: left; color: #999; text-transform: uppercase; font-size: .7rem;
    font-weight: normal; padding: .4rem .5rem; border-bottom: 1px solid #333; }}
  td {{ padding: .3rem .5rem; border-bottom: 1px solid #222; font-size: .85rem; }}
  td.date {{ color: #999; white-space: nowrap; }}
  td.dur {{ color: #bbb; white-space: nowrap; }}
  input {{ background: #1b1b1b; border: 1px solid #333; border-radius: 4px; color: #eee;
    padding: .3rem .4rem; font: inherit; width: 100%; }}
  input:focus {{ outline: none; border-color: #3987e5; }}
  input.time {{ width: 5.5rem; }}
  button {{ background: #2e2e2b; border: 0; border-radius: 999px; color: #bbb; cursor: pointer;
    padding: .35rem .9rem; font-size: .75rem; text-transform: uppercase; transition: background .15s ease; }}
  button:hover {{ background: #3987e5; color: #fff; }}
  .ver {{ color: #666; font-size: .7rem; margin-top: 2rem; }}
</style>
</head>
<body>
{menu}
<h1>{count} dernières lignes du CSV</h1>
{flash}
{forms}
<table>
<tr><th>date</th><th>projet</th><th>tâche</th><th>début</th><th>fin</th><th>durée</th><th></th></tr>
{rows}
</table>
<footer class="ver">v{version}</footer>
<script>
// durée affichée = fin − début, recalculée à la saisie ; le serveur reste seul
// juge au moment de l'enregistrement.
for (const form of document.querySelectorAll('form.rowform')) {{
  const cell = document.getElementById('dur-' + form.id);
  const mins = v => {{ const [h, m] = v.split(':'); return +h * 60 + +m; }};
  const refresh = () => {{
    const d = mins(form.endTime.value) - mins(form.startTime.value);
    cell.textContent = isNaN(d) || d <= 0 ? '—' : d + ' min';
  }};
  form.startTime.addEventListener('input', refresh);
  form.endTime.addEventListener('input', refresh);
}}
</script>
</body>
</html>
"""


def _rows_markup(rows):
    """(forms, trs) — une ligne de table = un <form> POST. Le <form> lui-même
    vit hors de la table (un <form> dans un <tr> est du HTML invalide) et porte
    la clé d'origine en champs cachés ; les champs visibles s'y rattachent par
    l'attribut `form=` (cf. update_csv_row : le CSV n'a pas d'identifiant)."""
    forms, trs = [], []
    for index, row in enumerate(rows):
        uid = f"r{index}"
        cell = {k: html.escape(str(row.get(k, ""))) for k in CSV_COLUMNS}
        forms.append(
            f'<form class="rowform" id="{uid}" method="post">'
            f'<input type="hidden" name="key_date" value="{cell["date"]}">'
            f'<input type="hidden" name="key_startTime" value="{cell["startTime"]}">'
            f'<input type="hidden" name="key_project" value="{cell["project"]}">'
            f'<input type="hidden" name="key_task" value="{cell["task"]}">'
            f"</form>"
        )
        trs.append(
            f"<tr>"
            f'<td class="date">{cell["date"]}</td>'
            f'<td><input form="{uid}" name="project" value="{cell["project"]}"></td>'
            f'<td><input form="{uid}" name="task" value="{cell["task"]}"></td>'
            f'<td><input form="{uid}" class="time" name="startTime" value="{cell["startTime"]}"></td>'
            f'<td><input form="{uid}" class="time" name="endTime" value="{cell["endTime"]}"></td>'
            f'<td class="dur" id="dur-{uid}">{cell["minutes"]} min</td>'
            f'<td><button form="{uid}" type="submit">Enregistrer</button></td>'
            f"</tr>"
        )
    return "\n".join(forms), "\n".join(trs)


@app.get("/swimlane", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/swimlane")
def swimlane(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    n = _int_arg("d") or SWIMLANE_DAYS
    n = max(SWIMLANE_MIN_DAYS, min(n, SWIMLANE_MAX_DAYS))
    days = swimlane_days(_read_csv_rows(CSV_PATH), datetime.now().date(), n=n)
    prefixes = {p for _, _, sessions in days for *_, p in sessions}
    fewer = (
        f'<a href="{prefix}/swimlane?d={n - 1}">−1 jour</a>'
        if n > SWIMLANE_MIN_DAYS else '<span class="disabled">−1 jour</span>'
    )
    more = (
        f'<a href="{prefix}/swimlane?d={n + 1}">+1 jour</a>'
        if n < SWIMLANE_MAX_DAYS else '<span class="disabled">+1 jour</span>'
    )
    nav = f'<p class="daynav">{fewer}<span class="day-label">{n} jours</span>{more}</p>'
    return SWIMLANE_HTML.format(
        days=n,
        menu=_menu_bar(prefix, "swimlane"),
        nav=nav,
        chart=render_swimlane_svg(days),
        legend=render_activity_legend_svg(_ordered_projects(prefixes)),
        version=APP_VERSION,
    )


@app.get("/live", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/live")
def live(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    weeks_back = _int_arg("w")
    monday, sunday = current_week_bounds(week_anchor(weeks_back))
    show_today = weeks_back == 0
    wq = f"?w={weeks_back}"

    if show_today:
        current_box = '<div id="current-box" class="empty">aucune tâche en cours</div>'
    else:
        current_box = ""

    newer = (
        f'<a href="{prefix}/live?w={weeks_back - 1}">{_CHEVRON_LEFT}semaine suivante</a>'
        if weeks_back > 0 else ""
    )
    older = f'<a href="{prefix}/live?w={weeks_back + 1}">semaine précédente{_CHEVRON_RIGHT}</a>'
    nav = (
        f'<p class="weeknav">{newer}'
        f'<span class="week-label">{_fr_week_range(monday, sunday)}</span>{older}</p>'
    )

    return LIVE_HTML.format(
        api_url=f"{prefix}/api/rows{wq}",
        week_url=f"{prefix}/billable-week.svg{wq}",
        activity_week_url=f"{prefix}/activity-week.svg{wq}",
        legend_url=f"{prefix}/activity-legend.svg{wq}",
        menu=_menu_bar(prefix, "live"),
        nav=nav,
        round_toggle=_round_toggle_html(_quantize_enabled()),
        current_box=current_box,
        version=APP_VERSION,
    )


def _int_arg(name):
    """Query param `name` as a non-negative int, 0 if missing or invalid."""
    try:
        return max(0, int(request.args.get(name, 0)))
    except (TypeError, ValueError):
        return 0


def _quantize_enabled():
    """Whether the 1/4h billable rounding is active, from the `round` cookie."""
    return request.cookies.get("round") == "1"


@app.get("/weeks", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/weeks")
def weeks(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    page = _int_arg("p")
    quantize = _quantize_enabled()
    blocks, prefixes = [], set()
    for monday, sunday, billable_days, activity_days in recent_weeks(page=page, quantize=quantize):
        for _, totals in activity_days:
            prefixes.update(totals)
        # pas de titre ici : chaque section porte déjà « Semaine du 23 au 29 juin »
        charts = render_week_svg(
            billable_days, bar_start=DAY_BAR_START_X, show_title=False,
        ) + render_activity_week_svg(
            activity_days, uid=monday.strftime("%Y%m%d"),
            bar_start=DAY_BAR_START_X, show_title=False,
        )
        blocks.append(
            f'<section class="week"><p class="week-label">'
            f'{_fr_week_range(monday, sunday)}</p>'
            f'<div class="week-charts">{charts}</div></section>'
        )
    legend = render_activity_legend_svg(_ordered_projects(prefixes))
    newer = (
        f'<a href="{prefix}/weeks?p={page - 1}">{_CHEVRON_LEFT}{BILLABLE_WEEKS_SHOWN} plus récentes</a>'
        if page > 0 else ""
    )
    older = f'<a href="{prefix}/weeks?p={page + 1}">{BILLABLE_WEEKS_SHOWN} plus anciennes{_CHEVRON_RIGHT}</a>'
    nav = f'<p class="weeknav">{newer}{older}</p>'
    return WEEKS_HTML.format(
        count=BILLABLE_WEEKS_SHOWN,
        page=page,
        menu=_menu_bar(prefix, "weeks"),
        nav=nav,
        round_toggle=_round_toggle_html(quantize),
        legend=legend,
        blocks="\n".join(blocks),
        version=APP_VERSION,
    )


@app.get("/months", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/months")
def months(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    n = _int_arg("n") or MONTH_WEEKS_SHOWN
    n = max(MONTH_MIN_WEEKS, min(n, MONTH_MAX_WEEKS))
    # la fenêtre ne démarre jamais plus de MONTH_MAX_WEEKS semaines en arrière
    page = min(_int_arg("p"), MONTH_MAX_WEEKS // n)
    quantize = _quantize_enabled()

    weeks = recent_week_totals(n=n, page=page, quantize=quantize)
    billable_rows = [(label, hours) for _, _, label, hours, _ in weeks]
    activity_rows = [(label, activity) for _, _, label, _, activity in weeks]
    prefixes = set()
    for _, activity in activity_rows:
        prefixes.update(activity)
    # Une ligne = une semaine : les maxima passent du jour (4h/8h) à la semaine
    # (20h/40h). Pas de barre de total ici (show_header=False) : la page compare
    # les semaines entre elles, le cumul sur N semaines n'apporte rien.
    month_groups = month_row_groups([monday for monday, _, _, _, _ in weeks])
    charts = render_week_svg(
        billable_rows,
        max_hours=BILLABLE_WEEK_MAX_HOURS,
        week_max_hours=BILLABLE_WEEK_MAX_HOURS * n,
        title_label=f"FACTURABLE — {n} SEMAINES",
        show_header=False,
        month_groups=month_groups,
    ) + render_activity_week_svg(
        activity_rows,
        max_hours=ACTIVITY_WEEK_MAX_HOURS,
        week_max_hours=ACTIVITY_WEEK_MAX_HOURS * n,
        uid="month",
        title_label=f"ACTIVITÉ — {n} SEMAINES",
        show_header=False,
        month_groups=month_groups,
    )

    # le réglage de n propage p : changer la taille de page ne doit pas ramener
    # en page 0
    fewer = (
        f'<a href="{prefix}/months?n={n - 1}&p={page}">{_CHEVRON_LEFT}−1 semaine</a>'
        if n > MONTH_MIN_WEEKS else f'<span class="disabled">{_CHEVRON_LEFT}−1 semaine</span>'
    )
    more = (
        f'<a href="{prefix}/months?n={n + 1}&p={page}">+1 semaine{_CHEVRON_RIGHT}</a>'
        if n < MONTH_MAX_WEEKS else f'<span class="disabled">+1 semaine{_CHEVRON_RIGHT}</span>'
    )
    newer = (
        f'<a href="{prefix}/months?n={n}&p={page - 1}">{_CHEVRON_LEFT}plus récentes</a>'
        if page > 0 else f'<span class="disabled">{_CHEVRON_LEFT}plus récentes</span>'
    )
    older = (
        f'<a href="{prefix}/months?n={n}&p={page + 1}">plus anciennes{_CHEVRON_RIGHT}</a>'
        if page < MONTH_MAX_WEEKS // n
        else f'<span class="disabled">plus anciennes{_CHEVRON_RIGHT}</span>'
    )
    nav = (
        f'<p class="weeknav">{fewer}<span class="week-count">{n} semaines</span>{more}</p>'
        f'<p class="weeknav">{newer}'
        f'<span class="week-count">{_fr_window(weeks)}</span>{older}</p>'
    )
    return MONTH_HTML.format(
        count=n,
        window=_fr_window(weeks),
        menu=_menu_bar(prefix, "month"),
        nav=nav,
        round_toggle=_round_toggle_html(quantize),
        charts=charts,
        legend=render_activity_legend_svg(_ordered_projects(prefixes)),
        version=APP_VERSION,
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
    w = _int_arg("w")
    monday, sunday = current_week_bounds(week_anchor(w))
    day_hours = billable_hours_for_days(
        monday, sunday, _read_csv_rows(CSV_PATH), quantize=_quantize_enabled()
    )
    highlight = day_label(datetime.now().date()) if w == 0 else None
    current_hours = 0.0
    if w == 0:
        current = current_task_row()
        if current and _row_is_billable(current):
            current_hours = current["minutes"] / 60
    svg = render_week_svg(
        day_hours, highlight_label=highlight, current_hours=current_hours,
        bar_start=DAY_BAR_START_X, title_label="FACTURABLE", title_totals=False,
    )
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
    w = _int_arg("w")
    _, sunday = current_week_bounds(week_anchor(w))
    days = activity_week_days(_read_csv_rows(CSV_PATH), sunday)
    highlight = day_label(datetime.now().date()) if w == 0 else None
    current_hours, current_prefix = 0.0, None
    if w == 0:
        current = current_task_row()
        if current:
            current_hours = current["minutes"] / 60
            current_prefix = _project_prefix(current["project"])
    svg = render_activity_week_svg(
        days, highlight_label=highlight,
        current_hours=current_hours, current_prefix=current_prefix,
        bar_start=DAY_BAR_START_X, title_label="ACTIVITÉS", title_totals=False,
    )
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/activity-legend.svg", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/activity-legend.svg")
def activity_legend_svg(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    rows = _read_csv_rows(CSV_PATH)
    anchor = week_anchor(_int_arg("w"))
    monday, _ = current_week_bounds(anchor)
    week_start, week_end = monday.strftime("%Y%m%d"), anchor.strftime("%Y%m%d")
    prefixes = set()
    for r in rows:
        if week_start <= r["date"] <= week_end:
            prefix = _project_prefix(r.get("project"))
            if prefix and prefix != "nan":
                prefixes.add(prefix)
    svg = render_activity_legend_svg(_ordered_projects(prefixes))
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


def _rows_flash():
    """Bandeau ok/erreur, passé par la query string au retour du POST (l'app
    n'a pas de SECRET_KEY, donc pas de flash Flask)."""
    if request.args.get("ok"):
        return '<p class="flash ok">Ligne enregistrée.</p>'
    err = request.args.get("err")
    if err:
        return f'<p class="flash err">{html.escape(err)}</p>'
    return ""


@app.get("/rows", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/rows")
def rows_page(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    n = _int_arg("n") or ROWS_SHOWN
    n = max(1, min(n, ROWS_MAX))
    rows = _read_csv_rows(CSV_PATH)
    rows.sort(key=lambda row: (row["date"], row["startTime"]), reverse=True)
    rows = rows[:n]
    forms, trs = _rows_markup(rows)
    return ROWS_HTML.format(
        count=len(rows),
        menu=_menu_bar(prefix, "rows"),
        flash=_rows_flash(),
        forms=forms,
        rows=trs,
        version=APP_VERSION,
    )


@app.post("/rows", defaults={"secret_path": ""})
@app.post("/<path:secret_path>/rows")
def rows_edit(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    prefix = f"/{secret_path.strip('/')}" if secret_path.strip("/") else ""
    form = request.form
    key = (
        form.get("key_date", ""),
        form.get("key_startTime", ""),
        form.get("key_project", ""),
        form.get("key_task", ""),
    )
    try:
        update_csv_row(
            key,
            form.get("project", "").strip(),
            form.get("task", "").strip(),
            form.get("startTime", "").strip(),
            form.get("endTime", "").strip(),
        )
    except RowEditError as exc:
        return redirect(f"{prefix}/rows?err={quote(str(exc))}")
    return redirect(f"{prefix}/rows?ok=1")


@app.get("/api/rows", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/api/rows")
def api_rows(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    weeks_back = _int_arg("w")
    today = datetime.now().strftime("%Y%m%d")
    rows = [r for r in _read_csv_rows(CSV_PATH) if r["date"] == today]
    rows.sort(key=lambda r: r["startTime"], reverse=True)
    current = current_task_row() if weeks_back == 0 else None
    return jsonify({"rows": rows, "current": current})


@app.get("/api/csv", defaults={"secret_path": ""})
@app.get("/<path:secret_path>/api/csv")
def csv_export(secret_path):
    if SECRET and secret_path.strip("/") != SECRET:
        return "not found\n", 404
    if not os.path.exists(CSV_PATH):
        return "not found\n", 404
    with open(CSV_PATH, encoding="utf-8") as f:
        body = f.read()
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "attachment; filename=pomofocus_webhook.csv",
        },
    )


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
