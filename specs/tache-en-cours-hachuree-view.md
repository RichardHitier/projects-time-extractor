# SPEC — Zone hachurée « tâche en cours » sur /view
Date : 2026-07-09
Statut : terminé

## Objectif (une phrase)
Voir en temps réel, sur la page /view, le temps déjà passé sur la tâche en
cours, matérialisé par une zone hachurée sur la barre du jour des deux graphes
semaine (gris sur le 20h facturable, couleur-projet sur le 40h activité).

## Critères de fin (3 max, observables)
- [x] Tâche en cours (semaine courante, w=0) → zone hachurée après le
      remplissage plein sur la barre du jour du graphe activité 40h, en couleur
      projet, qui grandit toute seule via le polling 3 s.
- [x] Sur le graphe facturable 20h : même zone hachurée en gris, uniquement si
      la tâche en cours est facturable.
- [x] Aucune hachure sur les semaines passées (w>0) ni sur /weeks, et pas de
      double comptage (tâche en cours pas encore dans le CSV).

## Hors scope — explicitement PAS dans cette feature
- Totaux et barres d'en-tête (/20h, /40h) inchangés : hachure sur la barre du
  jour uniquement.
- Débordement du max jour (4h/8h) géré par simple clamp dans la barre — pas de
  débordement doré hachuré.
- Pas de changement du current-box, du tableau, ni des autres pages
  (/swimlane, /weeks).

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1,5 h
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
Tout côté serveur (webhook_receiver.py). Le polling 3 s existant recharge les
SVG avec cache-bust → la hachure grandit toute seule.

| Tâche | Estimation |
|---|---|
| 1. Helper `_hatch_pattern(id, color)` (lignes diagonales 45°) | 10 min |
| 2. Hachure grise dans `render_week_svg` (param `current_hours`) | 15 min |
| 3. Hachure couleur-projet dans `render_activity_week_svg` (`current_hours`, `current_prefix`) | 15 min |
| 4. Câblage `billable_week_svg` / `activity_week_svg` (w==0 → `current_task_row()`) | 10 min |
| 5. Vérif script jetable (SVG dans scratchpad) | 5 min |
| **Total** | **55 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-09, ~40 min : implémenté (helper `_hatch_pattern` + hachure dans
  `render_week_svg`/`render_activity_week_svg` + câblage des 2 endpoints).
  Vérifié via script jetable → PNG : hachure gris/couleur-projet bien placée
  après le plein sur la ligne du jour, rien sur w>0. Les 3 critères cochés.
  Reste : contrôle en live sur /view (tâche réelle en cours) puis commit.
- 2026-07-09 : contrôle live OK (mock colibri), mock retiré, bump v0.5.0,
  commité sur main. Feature terminée.
