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

## Webhook live view — backlog

Suite de `/view` (`webhook_receiver.py`) : jauge d'heures facturables du jour
(`hh:min`, échelle 4h). Pas de code pour l'instant, à traiter petit à petit.

- [ ] **1. Merger `report.csv` dans le fichier webhook, renommé `report_webhook.csv`**
  `pomofocus.csv` n'est pas un export brut : c'est le résultat cumulé de
  merges successifs de `report.csv` (export pomofocus.io) via `pomo-merge` /
  `merge_pomo_exports` (`core/services.py:144`). On ne mergera donc pas
  `pomofocus.csv` dans le webhook, mais un **gros `report.csv`** (export complet
  pomofocus.io) directement avec le fichier webhook — qui sera renommé
  `pomofocus_webhook.csv` → `report_webhook.csv` (dans `webhook_receiver.py`
  et le volume `webhook-data/` de `docker-compose.yml`).
  Décision à prendre : stratégie de dédup — les deux fichiers se chevauchent
  sur les jours récents avec un grain différent : `report.csv` fusionne déjà
  les sessions **contiguës** de même clé `date, projet, tâche` en une seule
  ligne (avant même `pomo-merge`), alors que `pomofocus_webhook.csv` garde
  chaque session distincte telle que capturée, même contiguë et de même clé.
  Un merge naïf sur la clé habituelle `(date, startTime, project, task)` ne
  détecterait donc pas ces sessions contiguës comme des doublons et risque de
  compter le même temps deux fois.

- [x] **1-bis. Comprendre le flux `report.csv` → `pomofocus.csv` → `suivi_chantiers.ods`**
  `report.csv` (brut, pomofocus.io, `~/Téléchargements`) fusionne déjà, côté
  pomofocus.io, les sessions **contiguës** de même clé `date, projet, tâche`
  en une seule ligne — contrairement à `pomofocus_webhook.csv` qui garde le
  détail de chaque session même contiguë (cf. point 1). Ce `report.csv` est
  ensuite fusionné dans
  `DATA/pomofocus.csv` par `pomo-merge`/`merge_pomo_exports` (`core/services.py:144`,
  dédup `(date,startTime,endTime,project,task)` puis `(date,startTime,project,task)`
  en gardant le `endTime` le plus tardif ; ancien `pomofocus.csv` sauvegardé
  avec timestamp avant écrasement).
  `timer swimlane` lit `DATA/pomofocus.csv` (via `load_pomo_for_swimlane`,
  `core/services.py:91` → `load_all_pomo()`, `core/data.py`) — ni `report.csv`
  ni l'ODS.
  `suivi_chantiers.ods` (pas un CSV) est alimenté séparément par
  `timer report --view ods` (`report_view_ods`, `core/plots.py:192`), qui lit
  aussi `pomofocus.csv`. C'est cet ODS qui sert aux vues de facturation
  (`eighty-hours`, `eighty-bars`, `billing_export*` dans `core/suivi_chantier.py`).
  → deux consommateurs distincts de `pomofocus.csv`, aucun ne passe par le webhook.

- [ ] **2. Vue semaine sur `/view`** : heures facturables/4h des autres jours
  de la semaine, aujourd'hui en haut, plus anciens en bas, nom du jour en
  préfixe de ligne. Dépend du point 1 (il faut l'historique dans le fichier
  webhook). Décidé : en cas de dépassement de 4h, la barre déborde
  visuellement du repère 4h (pas de clamp à 100%), style distinct pour
  signaler le dépassement.

- [ ] **3. Couleurs par projet sur la barre facturable** : segmenter
  `/billable.svg` par projet, en réutilisant le champ `color` déjà présent
  par projet dans `projects-config.yml` (ex. `speasy: "#FFD43B"`,
  `calipso: "#4169E1"`, `pro: "#E03030"`, `perso: "#5A9931"`), via
  `load_projects()` (`config.py`). Fallback existant à reprendre si besoin :
  `_project_color_map` (`core/plots.py:241-269`, hash md5 → palette tab20/tab20b).

- [ ] **4. Swimlane — vue semaine complète sur `/view`** : pas juste une
  visualisation ponctuelle, mais le swimlane de toute la semaine courante.
  Agencement dans la page pas encore décidé. Décidé : réimplémentation SVG
  maison (pas de matplotlib/pandas dans le conteneur webhook), dans l'esprit
  de `render_billable_svg`. Référence CLI existante (non réutilisable telle
  quelle) : `plot_swimlane` (`core/plots.py:413-492`), lit `pomofocus.csv`.

- [ ] **a. Factoriser la lib commune** entre `webhook_receiver.py`
  (webhook_flask), `analysis_web.py` (analysis_flask) et `cli.py`/`core/`
  (timer_cli) — actuellement 3 pipelines distincts (cf. CLAUDE.md) qui
  dupliquent lecture CSV Pomofocus, couleurs par projet, calcul billable.
  À étudier : ce qui est partageable sans réintroduire pandas/matplotlib
  dans le conteneur webhook.

- [ ] **b. Étudier l'unification `analysis_web.py` / `webhook_receiver.py`**
  en une seule appli. À étudier : bénéfices vs coût (le webhook est
  volontairement minimal pour tourner en conteneur exposé publiquement).

- [ ] **c. Trancher SVG vs matplotlib** comme choix de rendu. Actuellement
  mixte : CLI/analysis = matplotlib, webhook = SVG maison (choix délibéré de
  légèreté). Décision à prendre : garder ce mix ou converger vers un seul
  choix partout.

- [ ] **d. Étudier précisément où et comment se fait l'arrondi au 1/4h.**
  Deux comportements différents identifiés aujourd'hui pour "les heures
  facturables" : `core/plots.py:143` (`report_view_export`, `quantize=True`)
  et `core/plots.py:171` (`_ods_data_row`, toujours actif) arrondissent
  chaque session au 1/4h supérieur (`math.ceil(duration_d / 0.03125) * 0.03125`)
  avant export/ODS ; la jauge webhook (`/billable.svg`) n'arrondit plus du
  tout (somme brute des minutes, décision prise précédemment). À clarifier :
  laquelle est la référence, faut-il aligner les deux.
