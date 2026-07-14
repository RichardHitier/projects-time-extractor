# SPEC — edition-lignes-csv
Date : 2026-07-13
Statut : terminé

## Objectif (une phrase)
Une page qui liste les lignes du CSV du webhook (`pomofocus_webhook.csv`) et
permet d'en éditer une — projet, tâche, début, fin — la durée étant recalculée
automatiquement.

## Critères de fin (3 max, observables)
- [x] La page liste les N dernières lignes du CSV, avec un bouton « éditer »
      sur chacune.
- [x] J'édite projet / tâche / début / fin, je valide : la durée est recalculée
      et le CSV est réécrit.
- [x] La ligne modifiée se reflète dans `/view` (ou `/live`).

## Hors scope — explicitement PAS dans cette feature
- Suppression de ligne.
- Ajout de ligne à la main.
- Édition multiple / en masse.
- Authentification.
- Historique des modifications (undo).

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
Idée directrice : **zéro nouveau moteur de données**. Tout passe par les helpers
existants de `webhook_receiver.py` (`_read_csv_rows`, `_write_csv_rows`,
`merge_contiguous_sessions`, `_hhmm_to_hours`, `_menu_bar`). Seule brique
nouvelle : `update_csv_row`, sœur de `upsert_csv_row`.

Le CSV n'a pas d'identifiant : une ligne est repérée par la clé
`(date, startTime, project, task)` — or ce sont les champs qu'on édite. Le
formulaire porte donc la clé **d'origine** en champs cachés ; si aucune ligne
ne correspond au POST, on n'écrit rien. UX : formulaire inline (une ligne du
tableau = un `<form>`), date en lecture seule.

| Tâche | Estimation |
|---|---|
| 1. `update_csv_row()` — validation, recalcul des minutes, écriture | 15 min |
| 2. `ROWS_HTML` + route `GET /rows` + entrée de menu | 20 min |
| 3. Route `POST /rows` — applique l'édition, bandeau ok/erreur | 10 min |
| 4. Tests (4) | 15 min |
| **Total** | **~60 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.
Premier candidat à la coupe : le sélecteur `?n=` (50 dernières lignes en dur).

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-13 : spec + plan validés, exécution lancée.
- 2026-07-13 (~45 min, dans le budget) : `/rows` livrée — `update_csv_row` +
  `RowEditError`, `ROWS_HTML` + `_rows_markup` (formulaire inline via l'attribut
  `form=`, un `<form>` dans un `<tr>` étant du HTML invalide), routes GET/POST
  `/rows`, entrée « Lignes » au menu, 4 tests (45 au vert). Vérifié bout en bout
  sur un CSV jetable : liste OK, édition → minutes recalculées (25 → 45) et CSV
  réécrit, `/swimlane` reflète le nouveau projet, `fin <= début` refusé sans
  écriture. Reste : validation visuelle dans le navigateur, puis commit.
