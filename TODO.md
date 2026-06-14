# TODO

## refactor responsabilities

Objectif : séparer `core/plots.py` en trois modules aux responsabilités distinctes
(`core/views.py`, `core/ods.py`, `core/plots.py` pur matplotlib).

- [ ] **0. Écrire les tests unitaires** (étape primordiale avant tout refactor)
  - couvrir `report_view_table`, `report_view_export` (avec/sans quantize, export_name_map)
  - couvrir `report_view_ods` (mois courant, --month, feuille inconnue)
  - couvrir `yyyymm_to_sheet_name`

- [ ] **1. Créer `core/views.py`** — déplacer les 4 vues texte stdout :
  `report_view_table`, `report_view_project`, `report_view_projectlogs`, `report_view_export`

- [ ] **2. Créer `core/ods.py`** — déplacer le code ODS :
  `_FRENCH_MONTHS`, `_month_sheet_name`, `_ods_data_row`, `yyyymm_to_sheet_name`, `report_view_ods`

- [ ] **3. Nettoyer `core/plots.py`** — ne garder que :
  `_project_color_map`, `plot_day_bars`, `plot_swimlane`
  Supprimer les imports `odfpy`, `math`, `locale`, `re` devenus inutiles

- [ ] **4. Mettre à jour `cli.py`** — ajuster les imports depuis les nouveaux modules

- [ ] **5. Vérifier manuellement les 5 vues CLI** :
  `--view table`, `project`, `export`, `project-logs`, `ods`
  + `day-bars` et `swimlane`

- [ ] **6. Commit**

## Eightyhours

Commande `timer eighty-hours` — heures journalières facturables depuis le ODS.

Implémenté :
- ✅ Sortie CSV journalier `J;D;S;H;T` (stdout par défaut)
- ✅ `--month YYYY-MM` pour cibler le mois
- ✅ `--write-ods` pour écrire dans la feuille `eighty-hours` de `suivi_chantiers.ods`

À faire :
- [ ] **`--plot`** : bar chart des heures journalières (colonne H) sur le mois
  - PNG sauvegardé ou affiché selon `--show`
  - Style cohérent avec `day-bars`

## Suivi chantiers — plots

Réintégrer dans le CLI les deux plots de `core/suivi_chantier.py` :

- [ ] **`plot_all_projects`** : bar chart du total JOURS par date, tous projets confondus
- [ ] **`plot_by_project`** : un subplot par projet, même axe X partagé
