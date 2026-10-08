import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import suivi
import webhook_receiver

COMMANDES = [
    {"nom": "calipso_a", "projet": "calipso", "debut": "2025-10-01"},
    {"nom": "calipso_b", "projet": "calipso", "debut": "2025-12-05"},
    {"nom": "speasy", "projet": "speasy", "debut": "2025-10-01"},
]


def row(day, project, task, minutes):
    return {"date": day, "project": project, "task": task, "minutes": str(minutes),
            "startTime": "", "endTime": ""}


def test_commande_for_picks_the_last_started_commande():
    assert suivi.commande_for("calipso_iesa", "20251204", COMMANDES) == "calipso_a"
    assert suivi.commande_for("calipso_iesa", "20251205", COMMANDES) == "calipso_b"
    assert suivi.commande_for("calipso", "20260301", COMMANDES) == "calipso_b"


def test_commande_for_is_none_without_an_applicable_commande():
    assert suivi.commande_for("colibri_admin", "20260101", COMMANDES) is None
    # séance antérieure à la première commande du projet
    assert suivi.commande_for("calipso_iesa", "20240101", COMMANDES) is None


def test_month_lines_drops_sessions_without_commande_and_puts_latest_first():
    rows = [
        row("20251203", "speasy", "codec", 60),
        row("20251208", "calipso_iesa", "fix", 60),
        row("20251208", "speasy", "codec", 60),
        row("20251208", "colibri_admin", "compta", 60),  # sans commande
    ]
    lines = suivi.month_lines(rows, "202512", COMMANDES,
                              ["calipso", "speasy", "colibri"])
    assert [(line["date"], line["commande"]) for line in lines] == [
        ("20251208", "calipso_b"),
        ("20251208", "speasy"),
        ("20251203", "speasy"),
    ]


def test_load_facturation_missing_file_is_empty(tmp_path):
    assert suivi.load_facturation(tmp_path / "nope.yml") == {}


def test_month_lines_groups_by_task_and_rounds_up_to_the_quarter_hour():
    rows = [
        row("20251205", "calipso_iesa", "fix", 20),
        row("20251205", "calipso_iesa", "fix", 20),   # même tâche : 40 → 45 min
        row("20251205", "calipso_lees", "fix", 1),    # 1 → 15 min
        row("20251205", "perso", "sport", 60),        # hors projets exportés
        row("20251105", "speasy", "codec", 60),       # autre mois
    ]
    lines = suivi.month_lines(rows, "202512", COMMANDES, ["calipso", "speasy"])
    assert [(line["commande"], line["sous_projet"], line["jours"]) for line in lines] == [
        ("calipso_b", "iesa", 45 / 480),
        ("calipso_b", "lees", 15 / 480),
    ]


def test_totals_by_commande_and_format_jours():
    lines = [{"commande": "speasy", "jours": 0.5},
             {"commande": "calipso_b", "jours": 0.03125},
             {"commande": "speasy", "jours": 0.5}]
    assert suivi.totals_by_commande(lines) == {"calipso_b": 0.03125, "speasy": 1.0}
    assert suivi.format_jours(0.03125) == "0,03"
    assert suivi.format_jours(9.0) == "9,00"
    assert suivi.format_jours(-0.0001) == "0,00"
    assert suivi.format_jours(9.0, trim=True) == "9"
    assert suivi.format_jours(3.5, trim=True) == "3,5"


def test_shift_month_crosses_years():
    assert suivi.shift_month("202601", -1) == "202512"
    assert suivi.shift_month("202612", 1) == "202701"


def test_suivi_page_shows_the_month_by_commande(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row("20251204", "calipso_iesa", "avant", 240))
        writer.writerow(row("20251205", "calipso_iesa", "après", 480))
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: calipso_a, projet: calipso, debut: '2025-10-01'}\n"
        "  - {nom: calipso_b, projet: calipso, debut: '2025-12-05'}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/suivi?m=202512").get_data(as_text=True)

    assert "décembre 2025" in page
    assert "calipso_a</td><td class=\"ref\"></td><td class=\"num\">0,50</td>" in page
    assert "calipso_b</td><td class=\"ref\"></td><td class=\"num\">1,00</td>" in page
    assert 'href="/suivi?m=202511"' in page
    assert 'href="/suivi"' in page   # entrée de menu


def test_months_between_goes_from_newest_to_oldest():
    assert suivi.months_between("202511", "202602") == ["202602", "202601", "202512", "202511"]
    assert suivi.first_month(COMMANDES, "209901") == "202510"
    assert suivi.first_month([], "209901") == "209901"


def test_monthly_totals_match_the_month_sheets():
    rows = [
        row("20251204", "calipso_iesa", "a", 60),
        row("20251205", "calipso_iesa", "b", 50),    # → 60 min
        row("20260105", "calipso_lees", "c", 120),
        row("20260105", "speasy", "d", 30),
    ]
    table = suivi.monthly_totals(rows, ["202601", "202512"], COMMANDES, ["calipso", "speasy"])
    assert table == {
        "calipso_a": {"202512": 60 / 480},
        "calipso_b": {"202512": 60 / 480, "202601": 120 / 480},
        "speasy": {"202601": 30 / 480},
    }


def test_suivi_synthese_page_links_each_cell_to_its_month(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row("20251205", "calipso_iesa", "x", 480))
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: calipso_b, projet: calipso, debut: '2025-12-05'}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/suivi/synthese").get_data(as_text=True)

    assert "<th>déc. 25</th>" in page
    assert '<a href="/suivi?m=202512">1,00</a>' in page
    assert 'href="/suivi/synthese" class="active">Synthèse' in page


def test_month_lines_appends_the_month_adjustments_last():
    rows = [row("20260302", "speasy", "codec", 480)]
    ajustements = [
        {"mois": "202603", "commande": "speasy", "jours": -0.25, "motif": "saisie manuelle ODS"},
        {"mois": "202604", "commande": "speasy", "jours": 1, "motif": "autre mois"},
    ]
    lines = suivi.month_lines(rows, "202603", COMMANDES, ["speasy"], ajustements)
    assert [(line["date"], line["jours"], line["ajustement"]) for line in lines] == [
        ("20260302", 1.0, False),
        ("", -0.25, True),
    ]
    assert lines[-1]["description"] == "ajustement : saisie manuelle ODS"
    assert suivi.totals_by_commande(lines) == {"speasy": 0.75}
    table = suivi.monthly_totals(rows, ["202604", "202603"], COMMANDES, ["speasy"], ajustements)
    assert table == {"speasy": {"202603": 0.75, "202604": 1.0}}


def test_suivi_page_shows_adjustments_as_dated_dash_lines(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row("20260302", "speasy", "codec", 480))
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: speasy, projet: speasy, debut: '2025-10-01'}\n"
        "ajustements:\n"
        "  - {mois: '202603', commande: speasy, jours: -0.25, motif: saisie manuelle ODS}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/suivi?m=202603").get_data(as_text=True)

    assert '<tr class="adj"><td class="date">—</td>' in page
    assert "ajustement : saisie manuelle ODS" in page
    assert 'speasy</td><td class="ref"></td><td class="num">0,75</td>' in page


def test_commande_summary_computes_billed_and_remaining_days():
    commandes = [
        {"nom": "calipso_b", "projet": "calipso", "ref": "R1", "tjm": 540, "devis": 20,
         "debut": "2025-12-05"},
        {"nom": "speasy", "projet": "speasy", "tjm": 490, "devis": 60, "debut": "2025-10-01"},
    ]
    factures = [
        {"commande": "calipso_b", "jours": 18},
        {"commande": "calipso_b", "jours": 2},
        {"commande": "speasy", "jours": 4},
    ]
    summary = suivi.commande_summary(commandes, factures, {"calipso_b": 19.5, "speasy": 5})
    b, s = summary
    assert (b["nom"], b["ref"], b["facture"]) == ("calipso_b", "R1", 20)
    assert b["reste_a_facturer"] == -0.5          # facturé d'avance
    assert b["reste_a_facturer_ht"] == -270
    assert b["reste_a_realiser"] == 0.5
    assert b["devis_ht"] == 10800
    assert (s["reste_a_facturer"], s["reste_a_facturer_ht"]) == (1, 490)
    assert s["reste_a_realiser"] == 55


def test_suivi_synthese_page_shows_the_commandes_table(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(row("20251205", "speasy", "x", 960))   # 2 j
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: speasy, projet: speasy, ref: R9, tjm: 500, devis: 10, debut: '2025-10-01'}\n"
        "factures:\n"
        "  - {id: F1, date: '2025-12-20', commande: speasy, jours: 1}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/suivi/synthese").get_data(as_text=True)

    assert "<h2>Commandes</h2>" in page
    assert '<td class="ref">R9</td>' in page
    # exécuté 2, facturé 1, reste 1 j = 500 €, reste à réaliser 8
    assert ('<td class="num">2,00</td><td class="num">1,00</td><td class="num">1,00</td>'
            '<td class="num eur">500 €</td><td class="num">8,00</td>') in page


def test_invoice_register_uses_the_chosen_tva_quarter():
    commandes = [{"nom": "speasy", "projet": "speasy", "tjm": 490, "debut": "2025-10-01"}]
    factures = [
        {"id": "F2", "date": "2026-08-05", "commande": "speasy", "jours": 4, "payee": None},
        # payée en février, déclarée au 2e trimestre : c'est mon choix, pas un calcul
        {"id": "F1", "date": "2026-01-29", "commande": "speasy", "jours": 9,
         "payee": "2026-02-23", "tva": "2T26"},
    ]
    register = suivi.invoice_register(factures, commandes, {"2T26": "2026-06-30"})
    first, second = register
    assert (first["id"], first["ht"], first["tva"], first["ttc"]) == ("F1", 4410, 882, 5292)
    assert (first["trimestre"], first["declaree"]) == ("2T26", "2026-06-30")
    assert (second["id"], second["payee"], second["trimestre"], second["declaree"]) == (
        "F2", "", "", "")


def test_suivi_factures_page_flags_unpaid_and_undeclared(tmp_path):
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: speasy, projet: speasy, tjm: 500, debut: '2025-10-01'}\n"
        "factures:\n"
        "  - {id: F1, date: '2026-07-01', commande: speasy, jours: 2, payee: '2026-07-10',"
        " tva: 3T26}\n"
        "  - {id: F2, date: '2026-08-01', commande: speasy, jours: 1, payee: '2026-08-10'}\n"
        "  - {id: F3, date: '2026-09-01', commande: speasy, jours: 1}\n",
        encoding="utf-8",
    )
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/suivi/factures").get_data(as_text=True)

    assert "<h2>Registre des factures</h2>" in page
    assert '<td class="todo">impayée</td>' in page                       # F3
    assert '<td class="date">3T26</td><td class="todo">à déclarer</td>' in page  # F1
    assert '<td class="date"></td><td class="todo">à déclarer</td>' in page      # F2
    assert '<td class="num eur">1 000 €</td>' in page   # HT de F1
    assert 'href="/suivi/factures" class="active">Factures' in page


LOTS_COMMANDES = [
    {"nom": "calipso_a", "projet": "calipso", "debut": "2025-10-01"},
    {"nom": "calipso_b", "projet": "calipso", "debut": "2025-12-05"},
    {"nom": "speasy", "projet": "speasy", "debut": "2025-10-01"},
]
LOTS_CATALOG = {"calipso": {"WP_1": "Banc", "WP_2": "IHM"},
                "speasy": {"JUICE_E2": "TF"}}


def test_invoice_lots_splits_days_by_lot_with_subtotals():
    factures = [
        {"id": "F3", "date": "2026-01-27", "commande": "calipso_b", "jours": 5,
         "lots": {"WP_1": 1, "WP_2": 4}},
        {"id": "F1", "date": "2025-11-18", "commande": "calipso_a", "jours": 3,
         "lots": {"WP_1": 3}},
        {"id": "F2", "date": "2025-12-19", "commande": "calipso_b", "jours": 2,
         "lots": {"WP_1": 1, "WP_2": 1}},
    ]
    (block,) = suivi.invoice_lots(factures, LOTS_COMMANDES, LOTS_CATALOG)
    assert block["projet"] == "calipso"
    assert block["lots"] == [("WP_1", "Banc"), ("WP_2", "IHM")]
    a, b = block["commandes"]
    assert (a["nom"], a["totaux"], a["jours"]) == ("calipso_a", {"WP_1": 3}, 3)
    assert [f["id"] for f in b["factures"]] == ["F2", "F3"]   # par date
    assert b["totaux"] == {"WP_1": 2, "WP_2": 5}
    assert (block["totaux"], block["jours"]) == ({"WP_1": 5, "WP_2": 5}, 10)
    assert all(f["ventilee"] and f["ecart"] == 0 for f in b["factures"])


def test_invoice_lots_flags_gaps_unsplit_and_unknown_lots():
    factures = [
        {"id": "F1", "date": "2026-01-29", "commande": "speasy", "jours": 9},
        {"id": "F2", "date": "2026-04-01", "commande": "speasy", "jours": 9,
         "lots": {"JUICE_E2": 8}},
        {"id": "F3", "date": "2026-06-19", "commande": "speasy", "jours": 1,
         "lots": {"AUTRE": 1}},
    ]
    (block,) = suivi.invoice_lots(factures, LOTS_COMMANDES, LOTS_CATALOG)
    first, second, third = block["commandes"][0]["factures"]
    assert (first["ventilee"], first["ecart"]) == (False, 9)
    assert (second["ventilee"], second["ecart"]) == (True, 1)
    assert block["lots"] == [("JUICE_E2", "TF"), ("AUTRE", "")]
    assert third["ecart"] == 0


def test_suivi_lots_page_has_one_table_per_project(tmp_path):
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: calipso_b, projet: calipso, debut: '2025-12-05'}\n"
        "  - {nom: speasy, projet: speasy, debut: '2025-10-01'}\n"
        "lots:\n"
        "  calipso: {WP_1: Banc, WP_2: IHM}\n"
        "  speasy: {JUICE_E2: TF}\n"
        "factures:\n"
        "  - {id: F1, date: '2026-01-27', commande: calipso_b, jours: 5,"
        " lots: {WP_1: 1, WP_2: 4}}\n"
        "  - {id: F2, date: '2026-04-01', commande: speasy, jours: 9}\n",
        encoding="utf-8",
    )
    webhook_receiver.FACTURATION_PATH = str(yml)
    page = webhook_receiver.app.test_client().get(
        "/suivi/lots").get_data(as_text=True)

    assert 'href="/suivi/lots" class="active">Lots' in page
    assert "<h2>calipso</h2>" in page and "<h2>speasy</h2>" in page
    assert '<abbr title="Banc">WP_1</abbr>' in page
    # F1 : 1 + 4 = 5, sans alerte ; F2 non ventilée
    assert ('<td class="num">1</td><td class="num">4</td>'
            '<td class="num">5</td><td></td></tr>') in page
    assert '<td class="todo">non ventilée</td>' in page


CALIPSO_C = {"nom": "calipso_c", "projet": "calipso", "tjm": 540,
             "debut": "2026-07-01",
             "devis_lots": {"WP_1": 6, "WP_2": 7, "WP_3": 7}}
CALIPSO_CATALOG = {"calipso": {"WP_1": "Banc", "WP_2": "IHM", "WP_3": "Tests"}}
CALIPSO_C_FACTURES = [
    {"id": "F1", "date": "2026-08-05", "commande": "calipso_c", "jours": 4,
     "lots": {"WP_1": 1, "WP_2": 3, "WP_3": 0}},
    # autre commande : ignorée
    {"id": "F0", "date": "2026-06-19", "commande": "calipso_b", "jours": 8,
     "lots": {"WP_1": 4, "WP_2": 3, "WP_3": 1}},
]


def test_next_invoice_splits_by_remaining_per_lot():
    # restes 5 / 4 / 7 ; 12 j → 3,75 / 3 / 5,25 → 4 / 3 / 5
    result = suivi.next_invoice(CALIPSO_C, CALIPSO_C_FACTURES, 12,
                                CALIPSO_CATALOG)
    assert [(lot["code"], lot["reste"], lot["jours"])
            for lot in result["lots"]] == [
        ("WP_1", 5, 4), ("WP_2", 4, 3), ("WP_3", 7, 5)]
    assert (result["jours"], result["hors_commande"]) == (12, 0)
    assert (result["ht"], result["ttc"]) == (6480, 6480 * 1.2)
    assert result["lots"][0]["libelle"] == "Banc"


def test_next_invoice_caps_each_lot_and_reports_the_overflow():
    result = suivi.next_invoice(CALIPSO_C, CALIPSO_C_FACTURES, 17,
                                CALIPSO_CATALOG)
    assert [lot["jours"] for lot in result["lots"]] == [5, 4, 7]
    assert (result["jours"], result["hors_commande"]) == (16, 1)


def test_next_invoice_breaks_ties_in_catalog_order():
    commande = {**CALIPSO_C, "devis_lots": {"WP_1": 2, "WP_2": 2}}
    # restes 2 / 2 ; 1 j → 0,5 / 0,5 → le premier lot du catalogue
    result = suivi.next_invoice(commande, [], 1, CALIPSO_CATALOG)
    assert [lot["jours"] for lot in result["lots"]] == [1, 0]


def test_next_invoice_single_lot_and_missing_devis():
    speasy = {"nom": "speasy", "projet": "speasy", "tjm": 490,
              "devis_lots": {"JUICE_E2": 60}}
    factures = [{"id": "F1", "date": "2026-01-29", "commande": "speasy",
                 "jours": 9, "lots": {"JUICE_E2": 9}}]
    result = suivi.next_invoice(speasy, factures, 3, {})
    assert [(lot["code"], lot["reste"], lot["jours"])
            for lot in result["lots"]] == [("JUICE_E2", 51, 3)]
    assert result["ht"] == 1470
    assert suivi.next_invoice({**speasy, "devis_lots": {}}, factures, 3,
                              {}) is None


def test_facturation_page_prefills_and_recomputes(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        # 2,5 j exécutés sur calipso_c, rien de facturé
        for day in ("20260701", "20260702", "20260703"):
            writer.writerow({"date": day, "project": "calipso_iesa",
                             "task": "t", "minutes": 480 if day < "20260703"
                             else 240, "startTime": "", "endTime": ""})
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: calipso_c, projet: calipso, tjm: 540, devis: 3,"
        " debut: '2026-07-01', devis_lots: {WP_1: 1, WP_2: 2}}\n"
        "lots:\n"
        "  calipso: {WP_1: Banc, WP_2: IHM}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/facturation").get_data(as_text=True)
    assert 'href="/facturation" class="active">Facturation' in page
    assert 'href="/facturation" class="active">Prochaine facture' in page
    assert 'href="/suivi/lots"' not in page   # hors des onglets de /suivi
    # 2,5 j → 2 j pré-remplis, ventilés 1/3 · 2/3 des restes 1 / 2 → 1 / 1
    assert 'name="j" min="0" step="1" value="2"' in page
    assert '<td class="num prop">1</td>' in page
    assert "todo" not in page.split("<h2>")[0].split("</form>")[1]

    page = client.get("/facturation?c=calipso_c&j=4").get_data(
        as_text=True)
    assert "on facturerait du temps non réalisé" in page
    assert "1 j au-delà du devis" in page


def test_module_totals_groups_by_subproject_and_adjustments():
    rows = [
        row("20251205", "calipso_iesa", "a", 240),
        row("20251206", "calipso_lees", "b", 480),
        row("20260105", "calipso_lees", "c", 120),
        row("20260105", "calipso", "d", 60),          # sans sous-projet
    ]
    ajustements = [{"mois": "202601", "commande": "calipso_b", "jours": 0.5}]
    table = suivi.module_totals(rows, ["202601", "202512"], COMMANDES,
                                ["calipso"], ajustements)
    assert table == {"calipso_b": {
        "iesa": {"202512": 0.5},
        "lees": {"202512": 1.0, "202601": 0.25},
        "—": {"202601": 0.125},
        "ajustements": {"202601": 0.5},
    }}
    # même total que la Synthèse
    monthly = suivi.monthly_totals(rows, ["202601", "202512"], COMMANDES,
                                   ["calipso"], ajustements)
    assert sum(sum(m.values()) for m in table["calipso_b"].values()) == sum(
        monthly["calipso_b"].values())


def test_facturation_activite_page_shows_modules_by_month(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=webhook_receiver.CSV_COLUMNS)
        writer.writeheader()
        for day, project, minutes in (("20260701", "calipso_lees", 480),
                                      ("20260702", "calipso_lees", 480),
                                      ("20260901", "calipso_iesa", 240),
                                      ("20260901", "speasy_hapi", 480)):
            writer.writerow({"date": day, "project": project, "task": "t",
                             "minutes": minutes, "startTime": "",
                             "endTime": ""})
    yml = tmp_path / "facturation.yml"
    yml.write_text(
        "commandes:\n"
        "  - {nom: calipso_c, projet: calipso, tjm: 540, debut: '2026-07-01'}\n"
        "  - {nom: speasy, projet: speasy, tjm: 490, debut: '2025-10-01'}\n",
        encoding="utf-8",
    )
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()

    page = client.get("/facturation/activite").get_data(as_text=True)
    assert 'href="/facturation/activite" class="active">Activité' in page
    assert "Activité par module — calipso_c" in page
    # lees 2 j (80 %), iesa 0,5 j ; août sans activité : pas de colonne
    assert ('<td>lees</td><td class="num tot">2,00</td>'
            '<td class="num pct">80%</td>') in page
    assert "<th>sept. 26</th><th>juil. 26</th>" in page
    assert "août" not in page

    page = client.get("/facturation/activite?c=speasy").get_data(
        as_text=True)
    assert "<td>hapi</td>" in page and "lees" not in page



EMIT_YML = (
    "# commentaire gardé\n"
    "commandes:\n"
    "  - {nom: calipso_c, projet: calipso, tjm: 540, devis: 20,"
    " debut: '2026-07-01', devis_lots: {WP_1: 6, WP_2: 7, WP_3: 7}}\n"
    "\n"
    "factures:\n"
    "  - {id: FA20260803, date: \"2026-08-05\", commande: calipso_c,"
    " jours: 4, lots: {WP_1: 1, WP_2: 3, WP_3: 0}}\n"
    "\n"
    "# TVA\n"
    "tva_declarations:\n"
    "  \"3T26\": \"2026-10-07\"\n"
)
EMIT_INVOICE = {"id": "FA20261008", "date": "2026-10-08",
                "commande": "calipso_c", "jours": 12,
                "lots": {"WP_1": 4, "WP_2": 3, "WP_3": 5}}


def test_check_invoice_accepts_a_valid_invoice_and_lists_errors():
    import yaml
    facturation = yaml.safe_load(EMIT_YML)
    assert suivi.check_invoice(facturation, EMIT_INVOICE) == []
    errors = suivi.check_invoice(facturation, {
        **EMIT_INVOICE, "id": "FA20260803", "date": "08/10/2026",
        "commande": "calipso_c", "lots": {"WP_1": 4, "WP_9": 1}})
    assert errors == [
        "n° FA20260803 déjà enregistré",
        "date « 08/10/2026 » : attendu aaaa-mm-jj",
        "lots hors devis : WP_9",
        "lots : 5 j ventilés pour 12 j facturés",
    ]


def test_append_invoice_inserts_after_the_last_invoice_only():
    line = suivi.invoice_yaml_line(EMIT_INVOICE)
    assert line == ('  - {id: FA20261008, date: "2026-10-08", '
                    "commande: calipso_c, jours: 12, "
                    "lots: {WP_1: 4, WP_2: 3, WP_3: 5}}\n")
    text = suivi.append_invoice(EMIT_YML, line)
    assert text == EMIT_YML.replace(
        "WP_3: 0}}\n", "WP_3: 0}}\n" + line, 1)
    assert suivi.append_invoice("commandes: []\n", line) == (
        "commandes: []\n\nfactures:\n" + line)


def test_facturation_emettre_writes_the_invoice_with_a_backup(tmp_path):
    yml = tmp_path / "facturation.yml"
    yml.write_text(EMIT_YML, encoding="utf-8")
    webhook_receiver.FACTURATION_PATH = str(yml)
    client = webhook_receiver.app.test_client()
    form = {"c": "calipso_c", "id": "FA20261008", "date": "2026-10-08",
            "jours": "12", "lot_WP_1": "4", "lot_WP_2": "3", "lot_WP_3": "5"}

    resp = client.post("/facturation/emettre", data=form)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(
        "/facturation?c=calipso_c&ok=FA20261008")
    text = yml.read_text(encoding="utf-8")
    assert "# commentaire gardé" in text and "# TVA" in text
    assert suivi.load_facturation(str(yml))["factures"][-1]["lots"] == {
        "WP_1": 4, "WP_2": 3, "WP_3": 5}
    (backup,) = (tmp_path / "bckp").iterdir()
    assert backup.read_text(encoding="utf-8") == EMIT_YML

    # même n° une seconde fois : refusé, rien d'écrit
    resp = client.post("/facturation/emettre", data=form)
    assert "err=" in resp.headers["Location"]
    assert yml.read_text(encoding="utf-8") == text


def test_facturation_page_has_the_emit_form_prefilled(tmp_path):
    csv_path = tmp_path / "pomofocus_webhook.csv"
    csv_path.write_text(",".join(webhook_receiver.CSV_COLUMNS) + "\n",
                        encoding="utf-8")
    yml = tmp_path / "facturation.yml"
    yml.write_text(EMIT_YML, encoding="utf-8")
    webhook_receiver.CSV_PATH = str(csv_path)
    webhook_receiver.FACTURATION_PATH = str(yml)
    page = webhook_receiver.app.test_client().get(
        "/facturation?c=calipso_c&j=5&ok=FA20261008").get_data(as_text=True)
    assert 'action="/facturation/emettre"' in page
    assert 'name="lot_WP_3"' in page
    assert 'name="jours" min="1" step="1" value="5"' in page
    assert "FA20261008 enregistrée dans facturation.yml" in page
