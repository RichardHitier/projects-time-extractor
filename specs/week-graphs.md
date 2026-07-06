# SPEC — week-graphs
Date : 2026-07-06
Statut : terminé

## Objectif (une phrase)
Remplacer le titre texte de chaque graphe semaine par une barre de progression
pleine largeur portant `nn / 20h` (billable) ou `nn / 60h` (activités).

## Critères de fin (3 max, observables)
- [x] Sur `/view`, le titre « Semaine : nn / 20h » du graphe billable est remplacé
      par une barre de progression pleine largeur, chiffre `nn / 20h` à droite.
- [x] Sur `/view`, le titre « Activité Semaine : nn » du graphe activité est remplacé
      par une barre pleine largeur, chiffre `nn / 60h` à droite.

## Hors scope — explicitement PAS dans cette feature
- Rendre les **graphes eux-mêmes** pleine largeur (≈ item Divers 07-05). À faire
  juste après, séparément.
- Extrapoler les barres à `/weeks` (#13 / #13-bis) — à décider après réflexion.
- Le highlight du jour courant sur `/weeks` (#12-bis).

## Budget
- Temps décidé : 15 min  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 22 min
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
| Tâche | Estimation |
|---|---|
| Helper `_week_header_bar` (barre + chiffre `nn/Nh` aligné) | 5 min |
| `render_week_svg` : titre → barre 20h (garde `<title>`) | 3 min |
| `render_activity_week_svg` : titre → barre 60h + const `ACTIVITY_WEEK_MAX_HOURS` | 4 min |
| Vérif : pytest + `/view` visuel | 3 min |
| **Total** | **15 min** |

Détail complet : `~/.claude/plans/passe-en-mode-plan-binary-crown.md`.

→ Si Total > Budget : couper du scope ICI, avant de coder.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-06 — ~15 min — helper `_week_header_bar` + 2 graphes semaine sur `/view` :
  titres texte → barres pleine largeur `nn/20h` / `nn/60h`, chiffre aligné avec les
  jours. `<title>` conservés. 26 tests verts (1 test route resserré). Critères OK.
  Reste : commit + clôture. Prochaine étape possible : extrapoler à `/weeks` (#13/#13-bis).
