import csv
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backfill_ods


def ods_df(rows):
    """DataFrame au schéma des feuilles mensuelles de suivi_chantiers.ods."""
    df = pd.DataFrame(rows, columns=["DATE", "PROJET", "SS-PROJET", "DESCRIPTION", "JOURS"])
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df


def write_csv(csv_path, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=backfill_ods.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_ods_row_maps_to_a_pomofocus_row_without_hours():
    df = ods_df([("2025-11-03", "calipso_b", "iesa", "revue", 0.125)])

    row = backfill_ods.ods_row_to_csv_row(df.iloc[0])

    assert row == {
        "date": "20251103",
        "project": "calipso_iesa",  # suffixe de contrat (_b) retiré
        "task": "revue",
        "minutes": 60,  # 0.125 j × 8 h
        "startTime": "",
        "endTime": "",
    }


def test_a_day_already_in_the_csv_is_left_alone():
    df = ods_df([
        ("2025-11-03", "calipso_b", "iesa", "revue", 0.125),
        ("2026-03-02", "speasy", "hapi", "déjà connu du webhook", 0.25),
    ])
    csv_rows = [{
        "date": "20260302", "project": "speasy_hapi", "task": "vraie session",
        "minutes": "120", "startTime": "09:00", "endTime": "11:00",
    }]

    new_rows = backfill_ods.rows_to_add(df, csv_rows)

    assert [row["date"] for row in new_rows] == ["20251103"]


def test_rows_after_until_are_ignored():
    df = ods_df([
        ("2026-02-18", "colibri", "admin", "avant la reprise", 0.125),
        ("2026-02-19", "colibri", "admin", "le CSV fait foi", 0.125),
    ])

    new_rows = backfill_ods.rows_to_add(df, [], until="20260218")

    assert [row["date"] for row in new_rows] == ["20260218"]


def test_running_the_backfill_twice_changes_nothing(tmp_path, monkeypatch):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    write_csv(csv_path, [{
        "date": "20260302", "project": "speasy_hapi", "task": "vraie session",
        "minutes": "120", "startTime": "09:00", "endTime": "11:00",
    }])
    df = ods_df([("2025-11-03", "calipso_b", "iesa", "revue", 0.125)])
    monkeypatch.setattr(backfill_ods, "read_ods_rows", lambda ods_path: df)
    monkeypatch.setattr(sys, "argv", ["backfill_ods.py", "--csv", str(csv_path)])

    backfill_ods.main()
    after_first = read_csv(csv_path)
    backfill_ods.main()

    assert len(after_first) == 2  # la ligne existante + celle de l'ODS
    assert read_csv(csv_path) == after_first
