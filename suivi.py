"""Suivi de facturation : portage de suivi_chantiers.ods dans l'appli web.

Fonctions pures, sans Flask ni pandas (le conteneur webhook n'a ni pandas ni
odfpy) : webhook_receiver.py lit les fichiers et leur passe les données.
Commandes et factures viennent de facturation.yml, rangé à côté de
pomofocus_webhook.csv dans le dossier de données.
"""
import re

import yaml

MINUTES_PER_DAY = 8 * 60  # un jour facturé = 8 h, comme core.data.duration_d


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
    facturé (colibri) ou séance antérieure à la première commande —, None."""
    prefix = (project or "").split("_", 1)[0].strip().lower()
    current = None
    for commande in sorted(commandes, key=lambda c: c["debut"]):
        debut = commande["debut"].replace("-", "")
        if commande["projet"] == prefix and debut <= day:
            current = commande["nom"]
    return current


def _clean(value):
    """Projet / tâche nettoyés comme core.data.read_pomo : guillemets retirés,
    « / » remplacé par « _ » (projet seulement), espaces repliés."""
    return re.sub(r"\s+", " ", (value or "").strip().strip('"'))


def month_lines(rows, yyyymm, commandes, projects, ajustements=(),
                round_minutes=15):
    """Lignes de la feuille du mois `yyyymm` (ex. '202609'), comme
    `timer report --view ods` les écrivait dans suivi_chantiers.ods.

    Séances des projets `projects` (préfixes, ex. EXPORT_PROJECTS) regroupées
    par (jour, projet, sous-projet, tâche), minutes sommées puis arrondies au
    multiple supérieur de `round_minutes` (BILLING_ROUND_MINUTES de
    config.yml), converties en jours de 8 h. Chaque ligne porte la
    commande du jour (commande_for) ; une séance sans commande applicable
    (projet non facturé comme colibri, ou antérieure à la première commande)
    est écartée. Triées par date décroissante (la plus récente en haut), puis
    commande.

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
        commande = commande_for(prefix, day, commandes)
        if commande is None:
            continue
        rounded = -(-minutes // round_minutes) * round_minutes
        lines.append({
            "date": day,
            "commande": commande,
            "sous_projet": sub,
            "description": task,
            "jours": rounded / MINUTES_PER_DAY,
            "ajustement": False,
        })
    lines.sort(key=lambda line: (line["commande"], line["sous_projet"],
                                 line["description"]))
    lines.sort(key=lambda line: line["date"], reverse=True)
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


def format_jours(days, trim=False):
    """Jours à 2 décimales, virgule décimale : 0.03125 → '0,03', 9.0 → '9,00'.
    Avec `trim`, sans zéros inutiles (jours facturés, en général entiers) :
    9.0 → '9', 3.5 → '3,5'."""
    text = f"{days:.2f}"
    if text == "-0.00":
        text = "0.00"
    if trim:
        text = text.rstrip("0").rstrip(".")
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


def monthly_totals(rows, months, commandes, projects, ajustements=(),
                   round_minutes=15):
    """{commande: {mois: jours}} pour chaque mois de `months` : les totaux par
    commande de month_lines(), ajustements compris, donc exactement ceux de la
    feuille du mois."""
    table = {}
    for month in months:
        lines = month_lines(rows, month, commandes, projects, ajustements,
                            round_minutes)
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


def invoice_register(factures, commandes, tva_declarations):
    """Tableau B de la Synthèse de l'ODS : une ligne par facture, par date
    d'émission. HT = jours × TJM de la commande, TVA 20 %, TTC.

    TVA sur les encaissements : le trimestre de déclaration d'une facture est
    choisi à la main (`tva` dans facturation.yml, ex. '3T26'), sa date de
    déclaration lue dans `tva_declarations`. Sans `tva`, la facture n'est pas
    encore rattachée à une déclaration.
    """
    tjms = {c["nom"]: float(c.get("tjm") or 0) for c in commandes}
    register = []
    by_date = sorted(factures, key=lambda f: (str(f["date"]), str(f["id"])))
    for facture in by_date:
        days = float(facture["jours"])
        tjm = tjms.get(facture["commande"], 0)
        ht = days * tjm
        paid = str(facture.get("payee") or "")
        quarter = str(facture.get("tva") or "")
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


def invoice_lots(factures, commandes, lots_catalog):
    """Ventilation des jours facturés par lot client, un bloc par projet (dans
    l'ordre des commandes de facturation.yml).

    `lots_catalog` = {projet: {code: libellé}} (`lots` de facturation.yml) ;
    chaque facture porte `lots: {code: jours}`. Un code absent du catalogue
    est quand même montré (libellé vide) ; une facture sans `lots` est non
    ventilée.

    Renvoie des dicts : projet, lots [(code, libellé)], commandes [{nom,
    factures, totaux, jours}], totaux {code: jours}, jours. Chaque facture :
    id, date, jours, lots {code: jours}, ventilee (bool), ecart (jours − somme
    des lots).
    """
    projects = []
    for commande in commandes:
        if commande["projet"] not in projects:
            projects.append(commande["projet"])
    by_commande = {}
    by_date = sorted(factures, key=lambda f: (str(f["date"]), str(f["id"])))
    for facture in by_date:
        by_commande.setdefault(facture["commande"], []).append(facture)

    blocks = []
    for project in projects:
        lots = dict((lots_catalog or {}).get(project) or {})
        block_commandes = []
        for commande in commandes:
            if commande["projet"] != project:
                continue
            rows = []
            for facture in by_commande.get(commande["nom"], []):
                split = {code: float(days) for code, days
                         in (facture.get("lots") or {}).items()}
                for code in split:
                    lots.setdefault(code, "")
                days = float(facture["jours"])
                rows.append({
                    "id": str(facture["id"]),
                    "date": str(facture["date"]),
                    "jours": days,
                    "lots": split,
                    "ventilee": bool(split),
                    "ecart": days - sum(split.values()),
                })
            if not rows:
                continue
            block_commandes.append({
                "nom": commande["nom"],
                "factures": rows,
                "totaux": _sum_lots(row["lots"] for row in rows),
                "jours": sum(row["jours"] for row in rows),
            })
        if not block_commandes:
            continue
        blocks.append({
            "projet": project,
            "lots": list(lots.items()),
            "commandes": block_commandes,
            "totaux": _sum_lots(c["totaux"] for c in block_commandes),
            "jours": sum(c["jours"] for c in block_commandes),
        })
    return blocks


def _sum_lots(splits):
    """{code: jours} sommés sur plusieurs ventilations."""
    totals = {}
    for split in splits:
        for code, days in split.items():
            totals[code] = totals.get(code, 0) + days
    return totals


def next_invoice(commande, factures, days, lots_catalog):
    """Ventilation proposée de la prochaine facture de `commande` : `days`
    jours entiers répartis sur ses lots au prorata de leur reste (devis du lot
    − déjà facturé), par la méthode du plus fort reste — parties entières,
    puis un jour de plus aux plus grandes parties fractionnaires, à égalité
    dans l'ordre du catalogue —, sans dépasser le reste d'un lot.

    Lots dans l'ordre du catalogue du projet, puis ceux du devis absents du
    catalogue. Sans `devis_lots` sur la commande : None.

    Renvoie un dict : lots [{code, libelle, devis, facture, reste, jours,
    ht}], jours (ventilés), hors_commande (jours au-delà des restes), ht,
    tva, ttc.
    """
    devis = commande.get("devis_lots") or {}
    if not devis:
        return None
    labels = dict((lots_catalog or {}).get(commande["projet"]) or {})
    codes = [code for code in labels if code in devis]
    codes += [code for code in devis if code not in labels]
    billed = _sum_lots(
        {code: float(d) for code, d in (f.get("lots") or {}).items()}
        for f in factures if f["commande"] == commande["nom"]
    )
    remaining = {code: max(float(devis[code]) - billed.get(code, 0), 0)
                 for code in codes}

    total_remaining = sum(remaining.values())
    to_split = min(int(days), int(total_remaining))
    split = dict.fromkeys(codes, 0)
    if to_split > 0:
        quotas = {code: to_split * remaining[code] / total_remaining
                  for code in codes}
        split = {code: int(quotas[code]) for code in codes}
        by_fraction = sorted(
            codes, key=lambda code: (-(quotas[code] - split[code]),
                                     codes.index(code))
        )
        left = to_split - sum(split.values())
        for code in by_fraction:
            if left <= 0:
                break
            if split[code] < remaining[code]:
                split[code] += 1
                left -= 1

    tjm = float(commande.get("tjm") or 0)
    lots = [{
        "code": code,
        "libelle": labels.get(code, ""),
        "devis": float(devis[code]),
        "facture": billed.get(code, 0),
        "reste": remaining[code],
        "jours": split[code],
        "ht": split[code] * tjm,
    } for code in codes]
    ventiles = sum(split.values())
    ht = ventiles * tjm
    return {
        "lots": lots,
        "jours": ventiles,
        "hors_commande": max(int(days) - ventiles, 0),
        "tjm": tjm,
        "ht": ht,
        "tva": ht * TVA_RATE,
        "ttc": ht * (1 + TVA_RATE),
    }


def module_totals(rows, months, commandes, projects, ajustements=(),
                  round_minutes=15):
    """{commande: {module: {mois: jours}}} sur `months` : les lignes de
    month_lines() regroupées par sous-projet (le module : « iesa », « lees »),
    « — » pour une séance sans sous-projet, `ajustements` pour les ajustements
    du mois. Mêmes séances et même arrondi que monthly_totals() : la somme
    d'une commande est son exécuté de la Synthèse."""
    table = {}
    for month in months:
        for line in month_lines(rows, month, commandes, projects, ajustements,
                                round_minutes):
            if line["ajustement"]:
                module = "ajustements"
            else:
                module = line["sous_projet"] or "—"
            by_month = table.setdefault(line["commande"], {}).setdefault(
                module, {})
            by_month[month] = by_month.get(month, 0) + line["jours"]
    return table
