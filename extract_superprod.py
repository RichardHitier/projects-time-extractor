import json
from datetime import datetime
from pprint import pprint

from config import load_config

# Fonction pour convertir timestamp en date lisible
def ts_to_date(ts):
    return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

# Fonction pour calculer la durée en heures
def delta_hours(start_ts, end_ts):
    if start_ts is not None and end_ts is not None:
        return round((end_ts - start_ts) / (1000 * 60 * 60), 2)
    return None

# Chargement du fichier JSON
superprod_file = load_config()["SUPERPROD_FILEPATH"]
with open(superprod_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Extraction des projets
projects = data['project']['entities']
pprint(projects)

# sys.exit()
# Parcours et affichage des infos demandées
for project_id, project in projects.items():
    title = project.get('title', 'Sans titre')
    work_start = project.get('workStart', {})
    work_end = project.get('workEnd', {})

    print(f"Projet : {title}")
    for date_str in sorted(work_start.keys()):
        start_ts = work_start[date_str]
        end_ts = work_end.get(date_str)
        start = ts_to_date(start_ts)
        end = ts_to_date(end_ts) if end_ts else 'Non défini'
        delta = delta_hours(start_ts, end_ts)
        delta_str = f"{delta:>6.2f} h" if delta is not None else "?"
        # print(f"  - {date_str}: start = {start}, end = {end}, durée = {delta_str}")
        print(f"  - {date_str}:  durée = {delta_str}")
    print()
