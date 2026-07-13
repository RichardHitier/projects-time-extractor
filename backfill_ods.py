"""Complète pomofocus_webhook.csv avec les lignes de suivi_chantiers.ods.

Le CSV du webhook a un trou (dernière ligne le 08/02/2025, suivante le
19/02/2026) : le webhook n'existait pas encore. L'ODS, lui, couvre une partie de
cette période (feuilles oct_25 → juil_26). Ce script en tire des lignes au schéma
Pomofocus et les ajoute au CSV.

L'ODS n'a pas d'heures de début/fin : les lignes importées les laissent VIDES.
`/live`, `/weeks` et `/months` ne lisent que `minutes` ; `/swimlane`, qui
positionne les sessions dans la journée, ignore les lignes sans heure parsable.

Deux garde-fous contre les doublons :
  - `--until` (défaut 20260218) : au-delà, le CSV est la source de vérité ;
  - un jour déjà présent dans le CSV n'est jamais touché — donc ré-exécutable.

Séquence (le CSV local n'est qu'un miroir de la prod, cf. `timer web_sync`) :
    timer web_sync                    # pull du CSV de prod
    python backfill_ods.py --dry-run  # contrôle
    python backfill_ods.py            # sauvegarde .bak-<ts> puis écriture
    scp webhook-data/pomofocus_webhook.csv <vps>:/home/debian/timer/webhook-data/

À faire hors session de travail : entre le pull et le push, tout pomodoro terminé
en prod écrit une ligne qui serait écrasée.
"""
import argparse
import csv
import shutil
from datetime import datetime

import pandas as pd

from config import load_config

_config = load_config()
ODS_PATH = _config["ODS_FILEPATH"]
CSV_PATH = _config["WEBHOOK_POMOFOCUS_FILEPATH"]
CSV_COLUMNS = ["date", "project", "task", "minutes", "startTime", "endTime"]

# Dernier jour que l'ODS a le droit de remplir : le CSV reprend le 19/02/2026.
DEFAULT_UNTIL = "20260218"

HOURS_PER_DAY = 8  # 1 JOUR d'ODS = 8 h


def read_ods_rows(ods_path=ODS_PATH):
    """Les lignes utiles de l'ODS, comme le fait report() (core/suivi_chantier).
    Les feuilles `eighty-hours` (grille calendaire) et `Synthèse` (facturation)
    n'ont pas le schéma DATE/PROJET/SS-PROJET/DESCRIPTION/JOURS."""
    sheets = pd.read_excel(ods_path, engine="odf", sheet_name=None)
    monthly = [
        df.dropna() for name, df in sheets.items()
        if name not in ("eighty-hours", "Synthèse")
    ]
    df = pd.concat(monthly, ignore_index=True)
    df.columns = df.columns.str.strip()
    df["DATE"] = pd.to_datetime(df["DATE"])
    return df[df["JOURS"] > 0]


def ods_row_to_csv_row(row):
    """Une ligne d'ODS au schéma Pomofocus. Le projet perd son suffixe de contrat
    pour coller aux valeurs du CSV : calipso_b + iesa -> calipso_iesa."""
    project = str(row["PROJET"]).split("_", 1)[0]
    return {
        "date": row["DATE"].strftime("%Y%m%d"),
        "project": f"{project}_{row['SS-PROJET']}",
        "task": str(row["DESCRIPTION"]),
        "minutes": round(row["JOURS"] * HOURS_PER_DAY * 60),
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


def rows_to_add(ods_df, csv_rows, until=DEFAULT_UNTIL):
    """Les lignes ODS à injecter : jusqu'à `until`, et seulement pour les jours
    dont le CSV ne sait rien. C'est ce qui rend le script ré-exécutable."""
    known_days = {row["date"] for row in csv_rows}
    new_rows = []
    for _, ods_row in ods_df.iterrows():
        row = ods_row_to_csv_row(ods_row)
        if row["date"] > until or row["date"] in known_days:
            continue
        new_rows.append(row)
    return new_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ods", default=ODS_PATH)
    parser.add_argument("--csv", default=CSV_PATH)
    parser.add_argument("--until", default=DEFAULT_UNTIL,
                        help=f"dernier jour importable, AAAAMMJJ (défaut {DEFAULT_UNTIL})")
    parser.add_argument("--dry-run", action="store_true",
                        help="affiche ce qui serait ajouté, sans rien écrire")
    args = parser.parse_args()

    csv_rows = read_csv_rows(args.csv)
    new_rows = rows_to_add(read_ods_rows(args.ods), csv_rows, until=args.until)

    if not new_rows:
        print(f"{args.csv} : rien à ajouter (jours déjà présents ou postérieurs à {args.until})")
        return

    days = sorted({row["date"] for row in new_rows})
    minutes = sum(row["minutes"] for row in new_rows)
    print(f"{len(new_rows)} lignes à ajouter — {days[0]} → {days[-1]}, "
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
