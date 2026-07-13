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


def test_billable_minutes_quantize_rounds_each_task_up_to_quarter_hour():
    # Reproduit l'arrondi de l'export ODS : fusion par (projet, task) puis ceil
    # au 1/4h de chaque tâche, séparément.
    rows = [
        # même tâche en deux blocs non contigus : fusion 10+10=20 -> ceil -> 30
        {"date": "20260703", "project": "speasy_supermag", "task": "dev", "minutes": "10"},
        {"date": "20260703", "project": "speasy_supermag", "task": "dev", "minutes": "10"},
        # tâche distincte : 5 -> ceil -> 15
        {"date": "20260703", "project": "calipso_iesa", "task": "doc", "minutes": "5"},
        # non facturable : ignoré
        {"date": "20260703", "project": "colibri_dev", "task": "x", "minutes": "50"},
    ]

    # sans arrondi : somme brute inchangée
    assert webhook_receiver.billable_minutes(rows, "20260703") == 10 + 10 + 5
    # avec arrondi : ceil par tâche
    assert webhook_receiver.billable_minutes(rows, "20260703", quantize=True) == 30 + 15


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


def test_billable_week_svg_cookie_toggles_quarter_hour_rounding(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    today = date.today().strftime("%Y%m%d")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": today, "project": "calipso_iesa", "task": "t",
            "minutes": "5", "startTime": "10:00", "endTime": "10:05",
        })
    webhook_receiver.CSV_PATH = str(csv_path)
    client = webhook_receiver.app.test_client()

    raw = client.get("/billable-week.svg").get_data(as_text=True)
    assert "SEMAINE : 0:05 / 20h" in raw

    client.set_cookie("round", "1")
    rounded = client.get("/billable-week.svg").get_data(as_text=True)
    assert "SEMAINE : 0:15 / 20h" in rounded


def test_round_toggle_reflects_cookie(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    off_client = webhook_receiver.app.test_client()
    for path in ("/live", "/weeks"):
        off = off_client.get(path).get_data(as_text=True)
        assert "arrondi 1/4h" in off
        assert '<input type="checkbox" onchange' in off  # décoché par défaut

    on_client = webhook_receiver.app.test_client()
    on_client.set_cookie("round", "1")
    for path in ("/live", "/weeks"):
        on = on_client.get(path).get_data(as_text=True)
        assert '<input type="checkbox" checked onchange' in on


def test_weeks_page_has_unique_clip_ids(tmp_path):
    # Several activity SVGs are inlined in one HTML document; clipPath ids are
    # document-global there, so they must be unique or every week would clip to
    # the first week's bar (bars stop rounding at the wrong width).
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")

    html = webhook_receiver.app.test_client().get("/weeks").get_data(as_text=True)

    ids = re.findall(r'clipPath id="([^"]+)"', html)
    assert ids, "no clipPath ids rendered"
    assert len(ids) == len(set(ids)), "duplicate clipPath ids across weeks"


def test_api_rows_filters_to_today(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    today = date.today().strftime("%Y%m%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")

    with open(webhook_receiver.CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": today, "project": "calipso", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })
        writer.writerow({
            "date": yesterday, "project": "calipso", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })

    client = webhook_receiver.app.test_client()
    data = client.get("/api/rows").get_json()

    assert len(data["rows"]) == 1
    assert data["rows"][0]["date"] == today


def test_csv_route_serves_raw_file(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    with open(webhook_receiver.CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": "20260707", "project": "calipso", "task": "t",
            "minutes": "10", "startTime": "10:00", "endTime": "10:10",
        })
    expected = open(webhook_receiver.CSV_PATH, encoding="utf-8").read()

    response = webhook_receiver.app.test_client().get("/api/csv")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.get_data(as_text=True) == expected


def test_csv_route_404_when_file_missing(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "does-not-exist.csv")

    response = webhook_receiver.app.test_client().get("/api/csv")

    assert response.status_code == 404


def test_csv_route_rejects_wrong_secret(tmp_path, monkeypatch):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    with open(webhook_receiver.CSV_PATH, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS).writeheader()
    monkeypatch.setattr(webhook_receiver, "SECRET", "s3cret")
    client = webhook_receiver.app.test_client()

    assert client.get("/api/csv").status_code == 404
    assert client.get("/wrong/api/csv").status_code == 404
    assert client.get("/s3cret/api/csv").status_code == 200


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


def test_live_hides_today_charts_for_past_weeks(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    client = webhook_receiver.app.test_client()

    current = client.get("/live").get_data(as_text=True)
    assert '<div id="current-box"' in current
    assert 'id="billable"' not in current       # graphes du jour retirés de /live
    assert "/billable-week.svg?w=0" in current
    assert "semaine suivante" not in current  # w=0: no newer week

    past = client.get("/live?w=1").get_data(as_text=True)
    assert '<div id="current-box"' not in past  # live box hidden
    assert 'id="billable"' not in past          # daily charts hidden
    assert "/billable-week.svg?w=1" in past     # week charts follow the offset
    assert "/activity-week.svg?w=1" in past
    assert "semaine suivante" in past           # can page back to newer


def _write_rows(csv_path, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_recent_week_totals_sums_a_whole_week_into_one_row(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    _write_rows(csv_path, [
        # semaine du lundi 2026-06-29 : deux jours facturables + un jour perso
        {"date": "20260629", "project": "calipso_iesa", "task": "t",
         "minutes": "60", "startTime": "10:00", "endTime": "11:00"},
        {"date": "20260630", "project": "speasy_core", "task": "t",
         "minutes": "90", "startTime": "10:00", "endTime": "11:30"},
        {"date": "20260630", "project": "perso", "task": "t",
         "minutes": "30", "startTime": "14:00", "endTime": "14:30"},
    ])
    webhook_receiver.CSV_PATH = str(csv_path)
    today = date(2026, 7, 1)  # mercredi ; lundi = 2026-06-29

    weeks = webhook_receiver.recent_week_totals(today=today, n=3)

    assert len(weeks) == 3
    monday, sunday, label, billable, activity = weeks[0]
    assert (monday, sunday) == (date(2026, 6, 29), date(2026, 7, 5))
    assert label == "S27"
    assert billable == 2.5  # 60 + 90 min, le perso n'est pas facturable
    assert activity == {"calipso": 60, "speasy": 90, "perso": 30}
    # les semaines précédentes sont vides mais présentes, plus récente d'abord
    assert weeks[1][0] == date(2026, 6, 22)
    assert (weeks[1][3], weeks[1][4]) == (0, {})


def test_recent_week_totals_quantizes_each_day_to_the_quarter_hour(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    _write_rows(csv_path, [
        {"date": "20260629", "project": "calipso_iesa", "task": "t",
         "minutes": "5", "startTime": "10:00", "endTime": "10:05"},
        {"date": "20260630", "project": "calipso_iesa", "task": "t",
         "minutes": "20", "startTime": "10:00", "endTime": "10:20"},
    ])
    webhook_receiver.CSV_PATH = str(csv_path)
    today = date(2026, 7, 1)

    raw = webhook_receiver.recent_week_totals(today=today, n=1)[0][3]
    rounded = webhook_receiver.recent_week_totals(today=today, n=1, quantize=True)[0][3]

    assert raw == 25 / 60           # 5 + 20
    assert rounded == 45 / 60       # 15 + 30 : arrondi par jour, pas sur le total


def test_month_page_renders_one_row_per_week(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    client = webhook_receiver.app.test_client()

    page = client.get("/month?n=3").get_data(as_text=True)

    labels = re.findall(r">(S\d\d)</text>", page)
    assert len(labels) == 6            # 3 semaines × 2 colonnes (facturable, activité)
    assert len(set(labels)) == 3       # les mêmes 3 semaines des deux côtés
    # les maxima passent du jour à la semaine, et le total d'en-tête à N semaines
    assert "FACTURABLE — 3 SEMAINES : 0:00 / 60h" in page
    assert "ACTIVITÉ — 3 SEMAINES : 0:00 / 120h" in page


def test_month_page_defaults_and_clamps_the_week_count(tmp_path):
    webhook_receiver.CSV_PATH = str(tmp_path / "pomofocus_webhook.csv")
    client = webhook_receiver.app.test_client()

    default = client.get("/month").get_data(as_text=True)
    assert f"{webhook_receiver.MONTH_WEEKS_SHOWN} semaines" in default

    too_many = client.get("/month?n=99").get_data(as_text=True)
    assert f"{webhook_receiver.MONTH_MAX_WEEKS} semaines" in too_many
    assert "/month?n=53" not in too_many  # borne haute : plus de lien "+1"

    too_few = client.get("/month?n=1").get_data(as_text=True)
    assert f"{webhook_receiver.MONTH_MIN_WEEKS} semaines" in too_few
    assert "/month?n=1" not in too_few    # borne basse : plus de lien "−1"


def test_month_page_respects_the_round_cookie(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    _write_rows(csv_path, [
        {"date": date.today().strftime("%Y%m%d"), "project": "calipso_iesa",
         "task": "t", "minutes": "5", "startTime": "10:00", "endTime": "10:05"},
    ])
    webhook_receiver.CSV_PATH = str(csv_path)
    client = webhook_receiver.app.test_client()

    raw = client.get("/month?n=2").get_data(as_text=True)
    assert "FACTURABLE — 2 SEMAINES : 0:05 / 40h" in raw

    client.set_cookie("round", "1")
    rounded = client.get("/month?n=2").get_data(as_text=True)
    assert "FACTURABLE — 2 SEMAINES : 0:15 / 40h" in rounded


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
