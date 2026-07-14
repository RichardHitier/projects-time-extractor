import csv
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backfill_ods


def suivi_df(rows):
    """DataFrame au schéma des feuilles mensuelles de suivi_chantiers.ods."""
    df = pd.DataFrame(rows, columns=["DATE", "PROJET", "SS-PROJET", "DESCRIPTION", "JOURS"])
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df


def archive_df(rows):
    """DataFrame au schéma des feuilles mensuelles de « facturation projets.ods »
    (archive CAE). `minutes` n'existe que sur les feuilles récentes."""
    df = pd.DataFrame(rows, columns=["date", "projet/lot", "activité", "nb j", "minutes"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def suivi_rows(rows):
    return [backfill_ods.suivi_row_to_csv_row(r) for _, r in suivi_df(rows).iterrows()]


def write_csv(csv_path, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=backfill_ods.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── suivi_chantiers.ods ───────────────────────────────────────────────────────

def test_suivi_row_maps_to_a_pomofocus_row_without_hours():
    df = suivi_df([("2025-11-03", "calipso_b", "iesa", "revue", 0.125)])

    row = backfill_ods.suivi_row_to_csv_row(df.iloc[0])

    assert row == {
        "date": "20251103",
        "project": "calipso_iesa",  # suffixe de contrat (_b) retiré
        "task": "revue",
        "minutes": 60,  # 0.125 j × 8 h
        "startTime": "",
        "endTime": "",
    }


# ── archive CAE ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("bht2", "bht"),                  # même projet que le bht_dev du CSV
    ("Co-libri", "colibri"),
    ("admin perso", "perso_admin"),   # convention <projet>_<activité>
    ("admin pro", "pro_admin"),
    ("Sapie", "sapie"),
    ("heliopropa", "heliopropa"),
])
def test_archive_project_names_are_normalized(raw, expected):
    assert backfill_ods.normalize_archive_project(raw) == expected


def test_archive_minutes_column_wins_over_the_day_count():
    df = archive_df([
        ("2025-03-01", "bht2", "revue", 0.45, 180.0),  # minutes renseignée
        ("2023-10-18", "heliopropa", None, 0.125, None),  # -> 0.125 j × 8 h
    ])

    rows = [backfill_ods.archive_row_to_csv_row(r) for _, r in df.iterrows()]

    assert rows[0]["minutes"] == 180  # et non 0.45 × 8 × 60 = 216
    assert rows[1]["minutes"] == 60
    assert rows[1]["task"] == ""  # « activité » est vide plus d'une fois sur deux


def test_two_activities_on_the_same_day_and_project_are_two_rows():
    # heliopropa le 06/11/2023 : web 0,75 j ET tao 0,5 j — ce ne sont pas des
    # doublons, les deux doivent survivre
    df = archive_df([
        ("2023-11-06", "heliopropa", "web", 0.75, None),
        ("2023-11-06", "heliopropa", "tao", 0.5, None),
    ])

    rows = [backfill_ods.archive_row_to_csv_row(r) for _, r in df.iterrows()]

    assert [(r["task"], r["minutes"]) for r in rows] == [("web", 360), ("tao", 240)]


# ── garde-fous (communs aux deux sources) ─────────────────────────────────────

def test_a_day_already_in_the_csv_is_left_alone():
    candidates = suivi_rows([
        ("2025-11-03", "calipso_b", "iesa", "revue", 0.125),
        ("2026-03-02", "speasy", "hapi", "déjà connu du webhook", 0.25),
    ])
    csv_rows = [{
        "date": "20260302", "project": "speasy_hapi", "task": "vraie session",
        "minutes": "120", "startTime": "09:00", "endTime": "11:00",
    }]

    new_rows = backfill_ods.rows_to_add(candidates, csv_rows)

    assert [row["date"] for row in new_rows] == ["20251103"]


def test_rows_after_until_are_ignored():
    candidates = suivi_rows([
        ("2026-02-18", "colibri", "admin", "avant la reprise", 0.125),
        ("2026-02-19", "colibri", "admin", "le CSV fait foi", 0.125),
    ])

    new_rows = backfill_ods.rows_to_add(candidates, [], until="20260218")

    assert [row["date"] for row in new_rows] == ["20260218"]


def test_running_the_backfill_twice_changes_nothing(tmp_path, monkeypatch):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    write_csv(csv_path, [{
        "date": "20260302", "project": "speasy_hapi", "task": "vraie session",
        "minutes": "120", "startTime": "09:00", "endTime": "11:00",
    }])
    candidates = suivi_rows([("2025-11-03", "calipso_b", "iesa", "revue", 0.125)])
    monkeypatch.setattr(backfill_ods, "read_suivi_rows", lambda ods_path: candidates)
    monkeypatch.setitem(
        backfill_ods.READERS, "suivi", (lambda ods_path: candidates, "unused.ods"),
    )
    monkeypatch.setattr(sys, "argv", ["backfill_ods.py", "--csv", str(csv_path)])

    backfill_ods.main()
    after_first = read_csv(csv_path)
    backfill_ods.main()

    assert len(after_first) == 2  # la ligne existante + celle de l'ODS
    assert read_csv(csv_path) == after_first
