"""Suivi de facturation : portage de suivi_chantiers.ods dans l'appli web.

Fonctions pures, sans Flask ni pandas (le conteneur webhook n'a ni pandas ni
odfpy) : webhook_receiver.py lit les fichiers et leur passe les données.
Commandes et factures viennent de facturation.yml, rangé à côté de
pomofocus_webhook.csv dans le dossier de données.
"""
import re

import yaml

MINUTES_PER_DAY = 8 * 60  # un jour facturé = 8 h, comme core.data.duration_d
ROUND_MINUTES = 15  # arrondi des lignes de l'ODS : 1/32 de jour = 15 min


def load_facturation(path):
    """Contenu de facturation.yml ; fichier absent = rien de configuré."""
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def commande_for(project, day, commandes):
    """Commande d'une séance : la dernière commande du projet dont `debut` est
    au plus tard `day` (YYYYMMDD). Sans commande applicable — projet non
    facturé (colibri) ou séance antérieure à la première commande —, le
    préfixe du projet."""
    prefix = (project or "").split("_", 1)[0].strip().lower()
    current = None
    for commande in sorted(commandes, key=lambda c: c["debut"]):
        debut = commande["debut"].replace("-", "")
        if commande["projet"] == prefix and debut <= day:
            current = commande["nom"]
    return current or prefix


def _clean(value):
    """Projet / tâche nettoyés comme core.data.read_pomo : guillemets retirés,
    « / » remplacé par « _ » (projet seulement), espaces repliés."""
    return re.sub(r"\s+", " ", (value or "").strip().strip('"'))


def month_lines(rows, yyyymm, commandes, projects):
    """Lignes de la feuille du mois `yyyymm` (ex. '202609'), comme
    `timer report --view ods` les écrivait dans suivi_chantiers.ods.

    Séances des projets `projects` (préfixes, ex. EXPORT_PROJECTS) regroupées
    par (jour, projet, sous-projet, tâche), minutes sommées puis arrondies au
    quart d'heure supérieur, converties en jours de 8 h. Chaque ligne porte la
    commande du jour (commande_for). Triées par date puis commande.

    Renvoie des dicts : date (YYYYMMDD), commande, sous_projet, description,
    jours.
    """
    wanted = {p.lower() for p in projects}
    groups = {}
    for row in rows:
        day = row.get("date") or ""
        if not day.startswith(yyyymm):
            continue
        project = _clean(row.get("project")).replace("/", "_")
        prefix, _, sub = project.partition("_")
        if prefix.lower() not in wanted:
            continue
        key = (day, prefix, sub, _clean(row.get("task")))
        groups[key] = groups.get(key, 0) + int(row.get("minutes") or 0)
    lines = []
    for (day, prefix, sub, task), minutes in groups.items():
        rounded = -(-minutes // ROUND_MINUTES) * ROUND_MINUTES
        lines.append({
            "date": day,
            "commande": commande_for(prefix, day, commandes),
            "sous_projet": sub,
            "description": task,
            "jours": rounded / MINUTES_PER_DAY,
        })
    lines.sort(key=lambda line: (line["date"], line["commande"],
                                 line["sous_projet"], line["description"]))
    return lines


def totals_by_commande(lines):
    """{commande: jours} sur les lignes d'un mois, par ordre alphabétique."""
    totals = {}
    for line in lines:
        name = line["commande"]
        totals[name] = totals.get(name, 0) + line["jours"]
    return dict(sorted(totals.items()))


def format_jours(days):
    """Jours avec toute leur précision (multiples de 1/32), virgule décimale,
    sans zéros inutiles : 0.03125 → '0,03125', 9.0 → '9', 3.5 → '3,5'."""
    text = f"{days:.5f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def shift_month(yyyymm, delta):
    """'202609', -1 → '202608' ; '202612', +1 → '202701'."""
    index = int(yyyymm[:4]) * 12 + int(yyyymm[4:]) - 1 + delta
    return f"{index // 12}{index % 12 + 1:02d}"


def months_between(first, last):
    """Mois de `first` à `last` inclus (YYYYMM), du plus récent au plus ancien,
    comme les colonnes du tableau C de l'ODS."""
    months, month = [], last
    while month >= first:
        months.append(month)
        month = shift_month(month, -1)
    return months


def first_month(commandes, default):
    """Mois de début de la plus ancienne commande (YYYYMM), `default` sans
    commande."""
    debuts = [c["debut"].replace("-", "")[:6] for c in commandes]
    return min(debuts) if debuts else default


def monthly_totals(rows, months, commandes, projects):
    """{commande: {mois: jours}} pour chaque mois de `months` : les totaux par
    commande de month_lines(), donc exactement ceux de la feuille du mois."""
    table = {}
    for month in months:
        lines = month_lines(rows, month, commandes, projects)
        for name, days in totals_by_commande(lines).items():
            table.setdefault(name, {})[month] = days
    return dict(sorted(table.items()))
