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

Objectif : intégrer `billing_export_days()` de `suivi_chantier.py` dans le CLI
comme `timer report --view eightyhours`.

Sortie : CSV journalier `J;D;S;H;T` (lettres jour, nº jour, semaine ISO,
heures facturables, total hebdo le dimanche) + ligne `;;TOTAL;x,xx;`.

**Question de conception à trancher** : source des données
- **Option A — lire depuis le ODS** (comme aujourd'hui) : cohérent avec le
  fait que le ODS est la source de vérité facturable ; nécessite que le ODS
  soit à jour (`--view ods` lancé avant)
- **Option B — lire depuis pomofocus** (comme toutes les autres vues) :
  pipeline unifié, pas de dépendance ODS ; mais contourne la validation
  manuelle du ODS

- [ ] **0. Trancher Option A ou B**

- [ ] **1. Déplacer `billing_export_days()` dans `core/`**
  (dans `core/ods.py` si Option A, dans `core/views.py` si Option B)
  Corriger le nom : `heightyhours` → `eighty-hours` ✓

- [ ] **2. Ajouter `--view eightyhours` dans `cli.py`**
  Réutiliser `--month YYYYMM` pour cibler le mois (défaut : mois courant)

- [ ] **3. Supprimer le code dupliqué dans `suivi_chantier.py`**
  (ou supprimer le fichier entier si tout est migré)

- [ ] **4. Vérifier manuellement la sortie vs l'ancienne commande**

- [ ] **5. Commit**
