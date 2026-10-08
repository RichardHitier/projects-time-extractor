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
