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


def month_lines(rows, yyyymm, commandes, projects, ajustements=()):
    """Lignes de la feuille du mois `yyyymm` (ex. '202609'), comme
    `timer report --view ods` les écrivait dans suivi_chantiers.ods.

    Séances des projets `projects` (préfixes, ex. EXPORT_PROJECTS) regroupées
    par (jour, projet, sous-projet, tâche), minutes sommées puis arrondies au
    quart d'heure supérieur, converties en jours de 8 h. Chaque ligne porte la
    commande du jour (commande_for). Triées par date puis commande.

    Les `ajustements` du mois (facturation.yml : mois, commande, jours, motif)
    s'ajoutent en fin de feuille, sans date : ils alignent les jours retenus
    pour la facturation sur l'ODS sans toucher aux séances du CSV.

    Renvoie des dicts : date (YYYYMMDD, vide pour un ajustement), commande,
    sous_projet, description, jours, ajustement (bool).
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
            "ajustement": False,
        })
    lines.sort(key=lambda line: (line["date"], line["commande"],
                                 line["sous_projet"], line["description"]))
    for adjustment in ajustements:
        if str(adjustment["mois"]) != yyyymm:
            continue
        lines.append({
            "date": "",
            "commande": adjustment["commande"],
            "sous_projet": "",
            "description": f"ajustement : {adjustment.get('motif') or ''}",
            "jours": float(adjustment["jours"]),
            "ajustement": True,
        })
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


def monthly_totals(rows, months, commandes, projects, ajustements=()):
    """{commande: {mois: jours}} pour chaque mois de `months` : les totaux par
    commande de month_lines(), ajustements compris, donc exactement ceux de la
    feuille du mois."""
    table = {}
    for month in months:
        lines = month_lines(rows, month, commandes, projects, ajustements)
        for name, days in totals_by_commande(lines).items():
            table.setdefault(name, {})[month] = days
    return dict(sorted(table.items()))


def commande_summary(commandes, factures, executed):
    """Tableau A de la Synthèse de l'ODS : une ligne par commande, dans l'ordre
    de facturation.yml. `executed` = {commande: jours exécutés} (ajustements
    compris, cf. monthly_totals).

    Facturé = somme des jours des factures de la commande ; reste à facturer =
    exécuté − facturé (négatif si facturé d'avance) ; reste à réaliser = devis
    − exécuté (négatif si dépassement de commande).
    """
    billed = {}
    for facture in factures:
        name = facture["commande"]
        billed[name] = billed.get(name, 0) + float(facture["jours"])
    summary = []
    for commande in commandes:
        name = commande["nom"]
        tjm = float(commande.get("tjm") or 0)
        devis = float(commande.get("devis") or 0)
        done = executed.get(name, 0)
        to_bill = done - billed.get(name, 0)
        summary.append({
            "nom": name,
            "ref": str(commande.get("ref") or ""),
            "tjm": tjm,
            "devis": devis,
            "devis_ht": devis * tjm,
            "execute": done,
            "facture": billed.get(name, 0),
            "reste_a_facturer": to_bill,
            "reste_a_facturer_ht": to_bill * tjm,
            "reste_a_realiser": devis - done,
        })
    return summary


TVA_RATE = 0.20


def tva_quarter(day):
    """Trimestre de TVA d'une date 'YYYY-MM-DD' : '2026-08-11' → '2026T3'."""
    return f"{day[:4]}T{(int(day[5:7]) - 1) // 3 + 1}"


def invoice_register(factures, commandes, tva_declarations):
    """Tableau B de la Synthèse de l'ODS : une ligne par facture, par date
    d'émission. HT = jours × TJM de la commande, TVA 20 %, TTC.

    TVA sur les encaissements : une facture payée tombe dans le trimestre de
    son paiement (`trimestre`), déclaré à la date de `tva_declarations` (vide
    tant que le trimestre n'est pas déclaré). Une facture impayée n'a ni
    trimestre ni déclaration.
    """
    tjms = {c["nom"]: float(c.get("tjm") or 0) for c in commandes}
    register = []
    by_date = sorted(factures, key=lambda f: (str(f["date"]), str(f["id"])))
    for facture in by_date:
        days = float(facture["jours"])
        tjm = tjms.get(facture["commande"], 0)
        ht = days * tjm
        paid = str(facture.get("payee") or "")
        quarter = tva_quarter(paid) if paid else ""
        register.append({
            "id": str(facture["id"]),
            "date": str(facture["date"]),
            "commande": facture["commande"],
            "jours": days,
            "tjm": tjm,
            "ht": ht,
            "tva": ht * TVA_RATE,
            "ttc": ht * (1 + TVA_RATE),
            "payee": paid,
            "trimestre": quarter,
            "declaree": str((tva_declarations or {}).get(quarter) or ""),
        })
    return register
