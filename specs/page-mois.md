# SPEC — page-mois
Date : 2026-07-13
Statut : en cours

## Objectif (une phrase)
Une page `/month` qui affiche, semaine par semaine sur les N dernières semaines
(défaut 8, réglable par `?n=`), les heures facturables et le total activités.

## Critères de fin (3 max, observables)
- [ ] La page `/month` s'affiche et présente, pour les N semaines sélectionnées,
      deux colonnes côte à côte — facturable (/20h par semaine) et activité
      toutes confondues (/40h par semaine) — une ligne par semaine (label `S28`),
      chaque colonne portant son total en barre d'en-tête (20h×N / 40h×N).

## Hors scope — explicitement PAS dans cette feature
- Pas de navigation entre mois (prev/next).
- Pas de détail par jour.

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
Idée directrice : **zéro nouveau renderer**. `render_week_svg` et
`render_activity_week_svg` sont génériques sur le label de ligne — on leur passe
des semaines au lieu de jours (`max_hours` 20/40 par ligne, `week_max_hours`
20×N / 40×N en en-tête).

| Tâche | Estimation |
|---|---|
| 1. `recent_week_totals(today, n, quantize)` — agrégation par semaine | 15 min |
| 2. `title_label` optionnel sur les 2 renderers | 5 min |
| 3. Route `/month` + `MONTH_HTML` + entrée de menu | 20 min |
| 4. Tests | 15 min |
| 5. Vérification (croisement des totaux avec `/weeks`) | 5 min |
| **Total** | **~60 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.
Premier candidat à la coupe : la nav −1/+1 semaine (`?n=` seul suffit au critère).

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-13 : spec + plan validés, exécution lancée.
- 2026-07-13 (~45 min, dans le budget) : `/month` livré — `recent_week_totals`,
  `title_label` sur les 2 renderers, route + `MONTH_HTML` + entrée de menu,
  5 tests (37 au vert). Totaux croisés avec `/weeks` : identiques semaine par
  semaine sur les deux colonnes. Reste : validation visuelle de la page.
