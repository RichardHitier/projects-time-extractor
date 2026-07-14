"""Complète pomofocus_webhook.csv avec les relevés tenus avant le webhook.

Le CSV du webhook a un trou (dernière ligne le 08/02/2025, suivante le
19/02/2026 : le webhook n'existait pas encore) et ne commence qu'au 28/05/2024.
Deux ODS, tenus à la main, savent ce qui s'est passé avant :

  --source suivi    suivi_chantiers.ods (feuilles oct_25 → juil_26)
                    colonnes DATE, PROJET, SS-PROJET, DESCRIPTION, JOURS
  --source archive  ~/00PRO/archives/cae-sapie-2022/facturation projets.ods
                    (feuilles Sept_22 → Juin_25)
                    colonnes date, projet/lot, activité, nb j, minutes

Aucun des deux n'a d'heure de début/fin : les lignes importées les laissent
VIDES. `/live`, `/weeks` et `/months` ne lisent que `minutes` ; `/swimlane`, qui
positionne les sessions dans la journée, ignore les lignes sans heure parsable.

Deux garde-fous contre les doublons :
  - `--until` (défaut 20260218) : au-delà, le CSV est la source de vérité ;
  - un jour déjà présent dans le CSV n'est jamais touché — donc ré-exécutable,
    et pas de double comptage avec les jours que le webhook connaît déjà.

Séquence (le CSV local n'est qu'un miroir de la prod, cf. `timer web_sync`) :
    timer web_sync                                  # pull du CSV de prod
    python backfill_ods.py --dry-run                # contrôle
    python backfill_ods.py                          # sauvegarde .bak-<ts>
    python backfill_ods.py --source archive
    scp webhook-data/pomofocus_webhook.csv <vps>:/home/debian/timer/webhook-data/

À faire hors session de travail : entre le pull et le push, tout pomodoro terminé
en prod écrit une ligne qui serait écrasée.
"""
import argparse
import csv
import os
import shutil
from datetime import datetime

import pandas as pd

from config import load_config

_config = load_config()
ODS_PATH = _config["ODS_FILEPATH"]
ARCHIVE_PATH = os.path.expanduser(
    "~/00PRO/archives/cae-sapie-2022/facturation projets.ods"
)
CSV_PATH = _config["WEBHOOK_POMOFOCUS_FILEPATH"]
CSV_COLUMNS = ["date", "project", "task", "minutes", "startTime", "endTime"]

# Dernier jour que les ODS ont le droit de remplir : le CSV reprend le 19/02/2026.
DEFAULT_UNTIL = "20260218"

HOURS_PER_DAY = 8  # 1 jour d'ODS = 8 h

# Noms de projets de l'archive → convention du CSV (<projet>_<activité>, en
# minuscules). `bht2` et `bibheliotech` désignent le même projet que le `bht_dev`
# du CSV (BibHelioTech) : on les fusionne sous `bht` pour garder un historique,
# une couleur et une ligne de légende uniques.
ARCHIVE_PROJECT_ALIASES = {
    "bht2": "bht",
    "bibheliotech": "bht",
    "co-libri": "colibri",
    "admin perso": "perso_admin",
    "admin pro": "pro_admin",
}


def read_suivi_rows(ods_path=ODS_PATH):
    """suivi_chantiers.ods → lignes au schéma CSV. Les feuilles `eighty-hours`
    (grille calendaire) et `Synthèse` (facturation) ont un autre schéma."""
    sheets = pd.read_excel(ods_path, engine="odf", sheet_name=None)
    monthly = [
        df.dropna() for name, df in sheets.items()
        if name not in ("eighty-hours", "Synthèse")
    ]
    df = pd.concat(monthly, ignore_index=True)
    df.columns = df.columns.str.strip()
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df[df["JOURS"] > 0]
    return [suivi_row_to_csv_row(row) for _, row in df.iterrows()]


def suivi_row_to_csv_row(row):
    """Le projet perd son suffixe de contrat, pour coller aux valeurs du CSV :
    calipso_b + iesa -> calipso_iesa."""
    project = str(row["PROJET"]).split("_", 1)[0]
    return csv_row(
        row["DATE"],
        f"{project}_{row['SS-PROJET']}",
        str(row["DESCRIPTION"]),
        minutes=round(row["JOURS"] * HOURS_PER_DAY * 60),
    )


def normalize_archive_project(value):
    """« Co-libri » → colibri, « admin perso » → perso_admin, bht2 → bht."""
    name = str(value).strip().lower()
    return ARCHIVE_PROJECT_ALIASES.get(name, name).replace(" ", "_")


def read_archive_rows(ods_path=ARCHIVE_PATH):
    """L'archive CAE → lignes au schéma CSV. Les feuilles `Fact. IRAP` et `Suivi`
    ont un autre schéma ; certaines feuilles mensuelles sont vides.

    Deux lignes de même date et même projet ne sont PAS des doublons : ce sont
    deux activités du jour (heliopropa : web 0,75 j + tao 0,5 j) — on les garde.
    """
    sheets = pd.read_excel(ods_path, engine="odf", sheet_name=None)
    rows = []
    for name, df in sheets.items():
        if name in ("Fact. IRAP", "Suivi"):
            continue
        df = df.rename(columns=lambda c: str(c).strip())
        if "date" not in df.columns or "projet/lot" not in df.columns:
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["nb j"] = pd.to_numeric(df["nb j"], errors="coerce")
        df = df[df["date"].notna() & df["projet/lot"].notna() & (df["nb j"] > 0)]
        rows.extend(archive_row_to_csv_row(row) for _, row in df.iterrows())
    return rows


def archive_row_to_csv_row(row):
    """La colonne `minutes` n'existe que sur les feuilles récentes (28 lignes sur
    400) ; ailleurs on convertit les jours. `activité` est vide plus d'une fois
    sur deux — la tâche l'est alors aussi."""
    minutes = pd.to_numeric(row.get("minutes"), errors="coerce")
    if pd.isna(minutes):
        minutes = row["nb j"] * HOURS_PER_DAY * 60
    task = row.get("activité")
    return csv_row(
        row["date"],
        normalize_archive_project(row["projet/lot"]),
        "" if pd.isna(task) else str(task),
        minutes=round(minutes),
    )


def csv_row(day, project, task, minutes):
    """Une ligne au schéma Pomofocus, sans heures : les ODS n'en ont pas."""
    return {
        "date": day.strftime("%Y%m%d"),
        "project": project,
        "task": task,
        "minutes": minutes,
        "startTime": "",
        "endTime": "",
    }


def read_csv_rows(csv_path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_rows(rows, csv_path):
    """Même ordre que le webhook (webhook_receiver._write_csv_rows) : les lignes
    importées, sans heure, se rangent en tête de leur journée."""
    rows = sorted(rows, key=lambda r: (r["date"], r["startTime"], r["project"], r["task"]))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def rows_to_add(candidates, csv_rows, until=DEFAULT_UNTIL):
    """Les lignes à injecter : jusqu'à `until`, et seulement pour les jours dont
    le CSV ne sait rien. C'est ce qui rend le script ré-exécutable."""
    known_days = {row["date"] for row in csv_rows}
    return [
        row for row in candidates
        if row["date"] <= until and row["date"] not in known_days
    ]


READERS = {"suivi": (read_suivi_rows, ODS_PATH), "archive": (read_archive_rows, ARCHIVE_PATH)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(READERS), default="suivi")
    parser.add_argument("--ods", help="surcharge le chemin de l'ODS de --source")
    parser.add_argument("--csv", default=CSV_PATH)
    parser.add_argument("--until", default=DEFAULT_UNTIL,
                        help=f"dernier jour importable, AAAAMMJJ (défaut {DEFAULT_UNTIL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="affiche ce qui serait ajouté, sans rien écrire")
    args = parser.parse_args()

    read_rows, default_ods = READERS[args.source]
    ods_path = args.ods or default_ods

    csv_rows = read_csv_rows(args.csv)
    new_rows = rows_to_add(read_rows(ods_path), csv_rows, until=args.until)

    if not new_rows:
        print(f"{args.csv} : rien à ajouter (jours déjà présents ou postérieurs à {args.until})")
        return

    days = sorted({row["date"] for row in new_rows})
    minutes = sum(row["minutes"] for row in new_rows)
    print(f"{args.source} : {len(new_rows)} lignes à ajouter — {days[0]} → {days[-1]}, "
          f"{minutes / 60:.1f} h ({minutes / 60 / HOURS_PER_DAY:.2f} jours)")
    for row in new_rows[:5]:
        print("   ", row)
    if len(new_rows) > 5:
        print(f"    … et {len(new_rows) - 5} autres")

    if args.dry_run:
        print("--dry-run : rien écrit.")
        return

    backup = f"{args.csv}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(args.csv, backup)
    write_csv_rows(csv_rows + new_rows, args.csv)
    print(f"sauvegarde : {backup}")
    print(f"écrit      : {args.csv} ({len(csv_rows) + len(new_rows)} lignes)")


if __name__ == "__main__":
    main()
