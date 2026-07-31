# SPEC — détail sous-projets

Date : 2026-07-31
Statut : en cours

## Objectif (une phrase)
Voir sur `/projects`, sous chaque projet facturable, la répartition des jours
consommés et du montant € par sous-projet (le segment après `_` : `colibri_dev`,
`colibri_admin`, `colibri_stage`…), depuis la date de dernière facture.

## Critères de fin (3 max, observables)
- [x] chaque projet tarifé affiche ses sous-projets en sous-lignes, avec jours
      et montant, depuis sa date de dernière facture
- [x] la somme des sous-lignes fait exactement la ligne projet, et le total du
      bas ne bouge pas (y compris avec l'arrondi 1/4 h activé)
- [x] un projet sans sous-projet (`project` sans `_`) reste affiché sans casser

## Hors scope — explicitement PAS dans cette feature
- Le détail par tâche (colonne `task`) — plus tard si besoin.
- Toute répartition temporelle (par semaine / par mois) du cumul.
- Les projets non tarifés : le tableau ne montre toujours que les facturables.
- `/live`, `/weeks`, `/months`, le CLI : page `/projects` uniquement.

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
| Tâche | Estimation |
|---|---|
| `project_minutes_by_subproject()`, dont `project_minutes_since()` devient la somme | 15 min |
| `project_subamounts()` (tri, projet à sous-projet unique) | 10 min |
| Sous-lignes + style sur `/projects` | 15 min |
| Tests | 15 min |
| **Total** | **55 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-31 — sous-lignes par sous-projet sur `/projects`.
  `project_minutes_since()` est maintenant la somme de
  `project_minutes_by_subproject()` : l'égalité détail/total tient par
  construction, arrondi 1/4 h compris, pas seulement par test. Un projet à
  sous-projet unique n'affiche pas de détail (la ligne projet dit déjà tout).
  Vérifié sur les données réelles : calipso 3 384 € = lees 2 428 + iesa 956.
