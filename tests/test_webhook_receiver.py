import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import webhook_receiver


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_payload_to_csv_row_exports_pomofocus_like_row():
    row = webhook_receiver.payload_to_csv_row({
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


def test_upsert_csv_row_keeps_latest_end_time(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"

    first = {
        "date": "20260701",
        "project": "calipso",
        "task": "June Tiny Fixes",
        "minutes": 5,
        "startTime": "12:00",
        "endTime": "12:05",
    }
    latest = {**first, "minutes": 25, "endTime": "12:25"}

    webhook_receiver.upsert_csv_row(first, csv_path)
    webhook_receiver.upsert_csv_row(latest, csv_path)

    assert read_rows(csv_path) == [{**latest, "minutes": "25"}]


def test_merge_contiguous_sessions_collapses_a_chain():
    rows = [
        {"date": "20260701", "project": "calipso", "task": "t", "minutes": "19", "startTime": "15:19", "endTime": "15:39"},
        {"date": "20260701", "project": "calipso", "task": "t", "minutes": "10", "startTime": "15:39", "endTime": "15:50"},
        {"date": "20260701", "project": "calipso", "task": "t", "minutes": "8", "startTime": "15:50", "endTime": "15:58"},
        {"date": "20260701", "project": "colibri", "task": "other", "minutes": "5", "startTime": "16:10", "endTime": "16:15"},
    ]

    merged = webhook_receiver.merge_contiguous_sessions(rows)

    assert merged == [
        {"date": "20260701", "project": "calipso", "task": "t", "minutes": 37, "startTime": "15:19", "endTime": "15:58"},
        {"date": "20260701", "project": "colibri", "task": "other", "minutes": "5", "startTime": "16:10", "endTime": "16:15"},
    ]


def test_upsert_csv_row_merges_contiguous_sessions(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"

    first = {
        "date": "20260701",
        "project": "calipso",
        "task": "June Tiny Fixes",
        "minutes": 19,
        "startTime": "15:19",
        "endTime": "15:39",
    }
    second = {
        "date": "20260701",
        "project": "calipso",
        "task": "June Tiny Fixes",
        "minutes": 10,
        "startTime": "15:39",
        "endTime": "15:50",
    }

    webhook_receiver.upsert_csv_row(first, csv_path)
    webhook_receiver.upsert_csv_row(second, csv_path)

    assert read_rows(csv_path) == [{
        "date": "20260701", "project": "calipso", "task": "June Tiny Fixes",
        "minutes": "29", "startTime": "15:19", "endTime": "15:50",
    }]


def test_upsert_csv_row_does_not_merge_non_contiguous_sessions(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"

    first = {
        "date": "20260701",
        "project": "calipso",
        "task": "June Tiny Fixes",
        "minutes": 19,
        "startTime": "15:19",
        "endTime": "15:39",
    }
    later = {**first, "minutes": 10, "startTime": "16:30", "endTime": "16:40"}

    webhook_receiver.upsert_csv_row(first, csv_path)
    webhook_receiver.upsert_csv_row(later, csv_path)

    assert read_rows(csv_path) == [
        {**first, "minutes": "19"},
        {**later, "minutes": "10"},
    ]


def test_billable_minutes_filters_by_day_and_project_without_rounding():
    rows = [
        {"date": "20260703", "project": "colibri_dev", "minutes": "50"},   # not billable
        {"date": "20260703", "project": "calipso_iesa", "minutes": "8"},   # billable: 8
        {"date": "20260703", "project": "speasy_supermag", "minutes": "20"},  # billable: 20
        {"date": "20260703", "project": "speasy_supermag", "minutes": "15"},  # billable: 15
        {"date": "20260702", "project": "speasy_supermag", "minutes": "60"},  # wrong day
    ]

    assert webhook_receiver.billable_minutes(rows, day="20260703") == 8 + 20 + 15


def test_billable_hours_reads_from_csv_path_for_given_day(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": "20260703", "project": "calipso_iesa", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })
        writer.writerow({
            "date": "20260702", "project": "calipso_iesa", "task": "t",
            "minutes": "45", "startTime": "10:00", "endTime": "10:45",
        })

    webhook_receiver.CSV_PATH = str(csv_path)

    assert webhook_receiver.billable_hours(day="20260703") == 10 / 60


def test_render_billable_svg_contains_value_and_is_valid_svg():
    svg = webhook_receiver.render_billable_svg(3.5, max_hours=4)

    assert svg.startswith("<svg")
    assert "FACTURABLE AUJOURD'HUI: 3:30 / 4h" in svg


def test_format_hm_rounds_to_nearest_minute():
    assert webhook_receiver._format_hm(1.9166) == "1:55"
    assert webhook_receiver._format_hm(4) == "4:00"
    assert webhook_receiver._format_hm(0) == "0:00"


def test_billable_svg_route_returns_svg(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    client = webhook_receiver.app.test_client()
    response = client.get("/billable.svg")

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert b"<svg" in response.data


def test_current_week_bounds():
    a_wednesday = date(2026, 7, 1)

    monday, sunday = webhook_receiver.current_week_bounds(a_wednesday)

    assert monday == date(2026, 6, 29)
    assert sunday == date(2026, 7, 5)


def test_billable_hours_for_week_returns_most_recent_first(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({  # Monday of the week
            "date": "20260629", "project": "calipso", "task": "t",
            "minutes": "30", "startTime": "10:00", "endTime": "10:30",
        })
        writer.writerow({  # Wednesday ("today" for this test)
            "date": "20260701", "project": "speasy", "task": "t",
            "minutes": "60", "startTime": "10:00", "endTime": "11:00",
        })
        writer.writerow({  # previous Sunday, must be excluded
            "date": "20260628", "project": "calipso", "task": "t",
            "minutes": "999", "startTime": "10:00", "endTime": "10:01",
        })

    webhook_receiver.CSV_PATH = str(csv_path)

    result = webhook_receiver.billable_hours_for_week(today=date(2026, 7, 1))

    assert result == [
        ("Mercredi", 1.0),
        ("Mardi", 0.0),
        ("Lundi", 0.5),
    ]


def test_render_week_svg_shows_labels_hours_and_overflow():
    svg = webhook_receiver.render_week_svg([("Vendredi", 5.5), ("Jeudi", 2.0)], max_hours=4)

    assert svg.startswith("<svg")
    assert "Vendredi" in svg
    assert "Jeudi" in svg
    assert "5:30" in svg
    assert "2:00" in svg
    assert "#d9a441" in svg  # overflow color, since 5.5h > max_hours=4


def test_render_week_svg_shows_week_header():
    svg = webhook_receiver.render_week_svg(
        [("Vendredi", 5.5), ("Jeudi", 2.0)], max_hours=4, week_max_hours=20
    )

    assert "SEMAINE : 7:30 / 20h" in svg


def test_render_week_svg_colors_today():
    svg = webhook_receiver.render_week_svg(
        [("Dimanche", 0.0), ("Mercredi", 3.0), ("Lundi", 2.0)],
        highlight_label="Mercredi",
    )
    assert 'stroke="#ffd43b" stroke-width="1.5"' in svg  # jour courant encadré en jaune
    assert 'fill="#c3c2b7">Lundi<' in svg                # autres jours inchangés
    plain = webhook_receiver.render_week_svg([("Mercredi", 3.0)])
    assert "#ffd43b" not in plain


def test_render_activity_week_svg_colors_today():
    svg = webhook_receiver.render_activity_week_svg(
        [("Mercredi", {"speasy": 60})], highlight_label="Mercredi"
    )
    assert 'stroke="#ffd43b" stroke-width="1.5"' in svg  # jour courant encadré en jaune


def test_billable_week_route_shows_full_week_and_colors_today(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    svg = webhook_receiver.app.test_client().get("/billable-week.svg").get_data(as_text=True)

    # semaine complète : 1 barre/jour lun..dim (hauteur 22 ; la barre d'en-tête
    # partage la couleur #2e2e2b mais fait hauteur 18)
    assert svg.count('height="22" rx="5" fill="#2e2e2b"') == 7
    assert 'stroke="#ffd43b" stroke-width="1.5"' in svg   # w=0 → jour courant encadré en jaune


def test_billable_week_svg_route_returns_svg(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    client = webhook_receiver.app.test_client()
    response = client.get("/billable-week.svg")

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert b"<svg" in response.data


def test_weeks_page_has_unique_clip_ids(tmp_path):
    # Several activity SVGs are inlined in one HTML document; clipPath ids are
    # document-global there, so they must be unique or every week would clip to
    # the first week's bar (bars stop rounding at the wrong width).
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    html = webhook_receiver.app.test_client().get("/weeks").get_data(as_text=True)

    ids = re.findall(r'clipPath id="([^"]+)"', html)
    assert ids, "no clipPath ids rendered"
    assert len(ids) == len(set(ids)), "duplicate clipPath ids across weeks"


def test_api_rows_filters_to_current_week(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    monday, _ = webhook_receiver.current_week_bounds()
    in_week = monday.strftime("%Y%m%d")
    out_of_week = (monday - timedelta(days=1)).strftime("%Y%m%d")

    with open(webhook_receiver.CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": in_week, "project": "calipso", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })
        writer.writerow({
            "date": out_of_week, "project": "calipso", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })

    client = webhook_receiver.app.test_client()
    data = client.get("/api/rows").get_json()

    assert len(data["rows"]) == 1
    assert data["rows"][0]["date"] == in_week


def test_hook_writes_jsonl_and_csv(tmp_path):
    webhook_receiver.LOG_PATH = str(tmp_path / "webhook_log.jsonl")
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    client = webhook_receiver.app.test_client()
    response = client.post("/", json={
        "round": "pomodoro",
        "type": "finish",
        "seconds": 1500,
        "session_start": 1711962000000,
        "session_end": 1711963500000,
        "project": "calipso",
        "task": "#42 auth: tests",
    })

    assert response.status_code == 200

    log_lines = Path(webhook_receiver.LOG_PATH).read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 1
    assert json.loads(log_lines[0])["json"]["type"] == "finish"

    assert read_rows(webhook_receiver.CSV_PATH) == [{
        "date": "20240401",
        "project": "calipso",
        "task": "#42 auth: tests",
        "minutes": "25",
        "startTime": "11:00",
        "endTime": "11:25",
    }]


def test_week_anchor_past_week_ends_on_sunday():
    today = date(2026, 7, 1)  # Wednesday; week Monday = 2026-06-29
    assert webhook_receiver.week_anchor(0, today=today) == today
    assert webhook_receiver.week_anchor(1, today=today) == date(2026, 6, 28)


def test_recent_weeks_page_shifts_window_by_count_weeks(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    today = date(2026, 7, 1)  # Wednesday; week Monday = 2026-06-29

    page0 = webhook_receiver.recent_weeks(today=today, count=12, page=0)
    page1 = webhook_receiver.recent_weeks(today=today, count=12, page=1)

    assert len(page0) == len(page1) == 12
    # page 0 starts at the current (partial) week: Monday..Wednesday = 3 days
    assert page0[0][0] == date(2026, 6, 29)
    assert len(page0[0][2]) == 3
    # page 1 is shifted 12 weeks back and spans complete Monday..Sunday weeks
    assert page1[0][0] == date(2026, 6, 29) - timedelta(weeks=12)
    assert page1[0][1] == page1[0][0] + timedelta(days=6)
    assert len(page1[0][2]) == 7
    # the windows are contiguous: page 1's newest week precedes page 0's oldest
    assert page1[0][0] == page0[-1][0] - timedelta(weeks=1)


def test_weeks_page_nav_links(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    client = webhook_receiver.app.test_client()

    first = client.get("/weeks").get_data(as_text=True)
    assert "plus récentes" not in first  # page 0: no newer window
    assert "/weeks?p=1" in first         # can page older

    p1 = client.get("/weeks?p=1").get_data(as_text=True)
    assert "/weeks?p=0" in p1             # newer
    assert "/weeks?p=2" in p1             # older


def test_view_hides_today_charts_for_past_weeks(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    client = webhook_receiver.app.test_client()

    current = client.get("/view").get_data(as_text=True)
    assert '<div id="current-box"' in current
    assert 'id="billable"' not in current       # graphes du jour retirés de /view
    assert "/billable-week.svg?w=0" in current
    assert "semaine suivante" not in current  # w=0: no newer week

    past = client.get("/view?w=1").get_data(as_text=True)
    assert '<div id="current-box"' not in past  # live box hidden
    assert 'id="billable"' not in past          # daily charts hidden
    assert "/billable-week.svg?w=1" in past     # week charts follow the offset
    assert "/activity-week.svg?w=1" in past
    assert "semaine suivante" in past           # can page back to newer


def test_api_rows_past_week_reports_no_current_task(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    webhook_receiver.CURRENT_TASK = {
        "date": "20260701", "project": "calipso", "task": "t", "start_ms": 1,
    }
    client = webhook_receiver.app.test_client()
    try:
        assert client.get("/api/rows?w=0").get_json()["current"] is not None
        assert client.get("/api/rows?w=1").get_json()["current"] is None
    finally:
        webhook_receiver.CURRENT_TASK = None
