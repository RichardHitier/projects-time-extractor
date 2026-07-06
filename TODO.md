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
(`hh:min`, échelle 4h). Traité petit à petit. Items regroupés par thème ci-dessous ;
les numéros/lettres sont des **ID stables** (références croisées « point 1 »,
« items 6 et d »…), pas un ordre de priorité.

> Livré hors items numérotés : activité par projet (segments colorés + légende
> partagée) sur `/view` **et** `/weeks` (chaque semaine porte le chart facturable
> + le chart activité côte à côte). Contexte pour #5 (navigation) et #13 (barre
> `nn/20h`), qui touchent la même page `/weeks`.

### A — Données & fiabilité backend

- [x] **1. Donner l'historique complet à `pomofocus_webhook.csv`**
  Fait en deux temps, sans renommage (le plan initial envisageait de fusionner
  un gros `report.csv` dans un fichier renommé `report_webhook.csv` — écarté
  au profit d'un backfill plus simple et plus sûr) :
  - `merge_contiguous_sessions` (`webhook_receiver.py`) fusionne désormais les
    sessions **contiguës** (même `date`/`project`/`task`, `endTime` ==
    `startTime` suivant) dans `pomofocus_webhook.csv`, pour retrouver le même
    grain que `pomofocus.csv`/`report.csv`. Appliqué à chaque écriture
    (`upsert_csv_row`) et rejoué une fois sur l'historique existant.
  - Backfill : les lignes de `DATA/pomofocus.csv` dont `date < 20260702`
    (première date présente côté webhook) ont été ajoutées telles quelles à
    `pomofocus_webhook.csv` (994 lignes). Les dates déjà couvertes par le
    webhook (02-03 juillet) n'ont **pas** été touchées : une comparaison a
    montré un écart réel entre les deux sources sur ces jours (ex. une session
    `speasy_supermag/studies` à 82 min côté `pomofocus.csv` contre 74+6+1=81
    min et un vrai trou de 5 min côté webhook) — `pomofocus.csv`/`report.csv`
    semble regrouper certaines sessions au-delà de la simple contiguïté
    (pause/reprise dans le timer), donc un merge naïf sur ces jours aurait pu
    désynchroniser les chiffres plutôt que juste dupliquer. Sauvegarde prise
    avant chaque modification du fichier réel (`webhook-data/*.bak-*`,
    supprimées une fois vérifiées).
  - [ ] **À vérifier** : les données d'avant mars manquent côté webhook —
    `suivi_chantiers.ods` en est-il alors la seule source ? (ex-Divers 07-05).

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

- [ ] **15. Cache mtime des lectures CSV**
  À chaque refresh (toutes les 3s), le CSV est relu et re-parsé 6× (`billable`,
  `week`, `activity`, `activity-week`, `legend`, `api`). Cache invalidé au
  `mtime` pour l'éviter.

- [ ] **16. Fixer le fuseau horaire**
  `_from_epoch_ms` (`webhook_receiver.py:58`) et « today » utilisent l'heure
  locale serveur (naïve) ; en conteneur la TZ peut différer → frontières de
  jour décalées. Épingler `Europe/Paris`.

- [ ] **18. Indicateur de fraîcheur**
  Afficher le dernier `mtime` du CSV / dernier webhook reçu, pour savoir que
  les données sont vivantes.

### B — Heures facturables & arrondi 1/4h

- [ ] **6. Calcul des heures facturables : « 1/4h commencé est dû »**
  La jauge webhook (`/billable.svg`) somme les minutes brutes ; il faut
  facturer chaque tranche de 1/4h commencée (arrondi au quart d'heure
  supérieur). Lié à l'étude point d (arrondi `math.ceil(duration_d / 0.03125)
  * 0.03125` déjà utilisé côté `report_view_export` / `_ods_data_row`).

- [ ] **8. Bascule visualisation comptage exact / arrondi 1/4h**
  Présenter les deux modes de comptage (minutes brutes vs arrondi au 1/4h
  supérieur, cf. items 6 et d) sur `/view`. Décidé (ex-Divers 07-06) : **bouton
  de bascule** sur le graphe 20h. Même mécanique de toggle que **#4** (swimlane /
  barres) — partager le composant plutôt que coder deux boutons.

- [ ] **d. Étudier précisément où et comment se fait l'arrondi au 1/4h.**
  Deux comportements différents identifiés aujourd'hui pour "les heures
  facturables" : `core/plots.py:143` (`report_view_export`, `quantize=True`)
  et `core/plots.py:171` (`_ods_data_row`, toujours actif) arrondissent
  chaque session au 1/4h supérieur (`math.ceil(duration_d / 0.03125) * 0.03125`)
  avant export/ODS ; la jauge webhook (`/billable.svg`) n'arrondit plus du
  tout (somme brute des minutes, décision prise précédemment). À clarifier :
  laquelle est la référence, faut-il aligner les deux.

### C — Jauge du jour (live)

- [ ] **9. Jauge du jour : débordement au-delà de 4h**
  `render_billable_svg` (`webhook_receiver.py:312`) clampe à `min(ratio, 1)` :
  au-delà de 4h la barre du jour n'indique rien. Harmoniser avec
  `render_week_svg`, qui gère déjà le débordement (marqueur + lane rouge).

- [ ] **10. Tâche en cours reflétée en temps réel**
  `CURRENT_TASK` / `current_task_row()` ne servent qu'au tableau ; les jauges
  `billable.svg` / `activity.svg` ne comptent que les sessions terminées.
  Ajouter un segment « en cours » (rayé/pulsant) pour un affichage live.

### D — Refactor week graphs

- [x] **2. Vue semaine sur `/view`** : heures facturables/4h des autres jours
  de la semaine, aujourd'hui en haut, plus anciens en bas, nom du jour en
  préfixe de ligne. Dépend du point 1 (il faut l'historique dans le fichier
  webhook). Décidé : en cas de dépassement de 4h, la barre déborde
  visuellement du repère 4h (pas de clamp à 100%), style distinct pour
  signaler le dépassement.

- [ ] **7. Vue semaine : barre graphique `nn / 20h`**
  Ajouter dans la vue semaine (`/billable-week.svg` ou le header) une barre
  graphique du total facturable de la semaine par rapport à l'objectif de
  20h (`nn / 20h`), sur le modèle de la jauge journalière `/4h`.
  cette barre remplace le titre "Semaine: 18,36 / 20h" et
  occupe toute la largeur du graphique , chiffre affiché à
  droite aligné avec lse chiffres jours

- [ ] **7-bis. Vue activitè : barre graphique `nn / 60h`**
   idem 7: on supprim le titre texte Activité Semaine: 29:46
   et on rajoute une barre de progression nn/60 qui occupe
   toute la largeur, chiffre affiché à droite aligné avec
   lse chiffres jours

- [ ] **12. Mise en relief du jour courant**
  Dans les vues semaine (`render_week_svg` / `render_activity_week_svg`), 
  La semaine courante (20h ou activités) doit maintenant
  montrer tous les jours mais **encadre le jour courant**
  (ex-Divers 07-06).


- [ ] **13. Barre `nn / 20h` dans `/weeks`**
  Réutiliser l'item 7 sur chaque semaine de la page `/weeks`


- [ ] **13-bis. Barre `nn / 60h` dans `/weeks`**
  Réutiliser l'item 7-bis sur chaque semaine de la page `/weeks`

### E — Navigation & layout de page

- [x] **5. Naviguer dans l'historique des semaines** — FAIT (e3616c2, spec
  `chart-weeks` terminé). `/weeks` pagine par fenêtres de 12 semaines via `?p=N`,
  `/view` décale d'une semaine via `?w=N` (boutons prev/next).

- [ ] **22. Layout de la vue live `/view`** : disposer la page en grille —
  ligne 1 `Semaine 20h` | `Semaine activités`, ligne 2 `heures du jour` |
  `activités du jour`, ligne 3 `Tâche courante` (sous les deux graphes du jour).
  En naviguant vers une semaine plus ancienne : ne garder **que** la ligne 1
  (`Semaine 20h` | `Semaine activités`) ; le jour et la tâche courante restent
  masqués (comportement actuel `webhook_receiver.py:955`, `weeks_back == 0`).
  (Ex-Divers 07-04/05/06.)
### F — Activité par projet (couleurs, swimlane, interactions)

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
  Décidé (ex-Divers 07-06) : le swimlane s'affiche **à la place** du graphe
  d'activité (aujourd'hui + semaine dans `/view`, chaque semaine dans `/weeks`),
  avec un **bouton** pour basculer présentation swimlane / barres.

- [ ] **11. Tooltips par segment projet**
  Les `<rect>` de `_activity_segments` n'ont pas de valeur ; un `<title>` par
  rect (projet + `hh:mm`) donnerait un survol natif, sans JS.

- [ ] **20. Légende cliquable / filtrage par projet**
  Activer/désactiver un projet dans les charts d'activité.

### G — Tests

- [ ] **17. Tests des rendus SVG**
  Couvrir `render_week_svg` (débordement), `render_activity_svg`, et le mapping
  `project_color` config vs hash, dans `test_webhook_receiver.py`.

### H — Déploiement

- [x] **21. Déploiement : push local → déploiement sur le VPS** — EN PROD
  Autodeploy sur `git push origin` (main). **GitHub Actions + SSH** (push-based),
  écarté le webhook GitHub → endpoint (le conteneur ne peut pas se
  reconstruire/redémarrer proprement lui-même). Validé le 2026-07-04 (run
  `28711971475`, 43s : build image → recreate `timer-webhook-1`/`timer-nginx-1`).
  - `deploy.sh` (racine) : `git reset --hard origin/main` + `docker compose
    build webhook` + `up -d` + `image prune`. Lancé sur l'hôte VPS
    (`/home/debian/timer`). `.env` / `webhook-data/` gitignorés → préservés.
  - `.github/workflows/deploy.yml` : sur push main (+ `workflow_dispatch`),
    SSH brut vers le VPS. **Amorçage** : le workflow fait `git fetch` +
    `reset --hard origin/main` AVANT `./deploy.sh` (sinon le script n'est pas
    encore présent au 1er run). `concurrency` = pas deux déploiements parallèles.
  - Setup fait : clé `gh_deploy` (pub → `authorized_keys` VPS, priv → secret
    GitHub `VPS_SSH_KEY`) + secrets `VPS_HOST`/`VPS_USER`/`VPS_PATH`.
  - Note : le hook pre-commit `pytest-fail` bloque `git push` hors venv
    (`pytest` introuvable) → pusher avec `--no-verify` ou `workon time_tracking`
    avant. Voir [[feedback_virtualenv]].

### I — Architecture (à étudier)

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

## Divers

- [ ] [2026-07-04] versionner
- [ ] [2026-07-05] menu de navigation, avec liens live + semaines facturables (harmoniser en pastilles comme les flèches prev/next)
- [ ] [2026-07-05] renommer la route /view → /live (ex « modifier le endpoint view en live »)
- [ ] [2026-07-05] présenter les graphes de l'accueil sur la lageur de la page
- [x] [2026-07-04] navigation semaines fwb/bckw : icones fleches
