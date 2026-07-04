# SPEC — chart-weeks
Date : 2026-07-04
Statut : terminé

## Objectif (une phrase)
Naviguer semaine par semaine dans `/weeks` (avant / arrière).

## Critères de fin (3 max, observables)
- [x] Boutons prev/next dans `/weeks` qui décalent la fenêtre de 12 semaines
- [x] Boutons prev/next dans `/view` qui décalent la fenêtre de 1 semaine

## Hors scope — explicitement PAS dans cette feature
- Endpoint `weeks/nn` (nombre de semaines paramétrable)
- `weeks/all`
- Vue mensuelle
- Sélecteur de date arbitraire

## Budget
- Temps décidé : 2 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 3 h
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
| Tâche | Estimation |
|---|---|
| A — pagination `/weeks` (`?p=`, `recent_weeks(page=)` + nav prev/next) | 30 min |
| B — navigation `/view` (`?w=`, anchor semaine, masquage des éléments « du jour ») | 55 min |
| C — tests + vérif manuelle | 35 min |
| **Total** | **2 h** |

→ Si Total > Budget : couper du scope ICI, avant de coder.

Détail complet : `~/.claude/plans/on-y-est-joyful-hejlsberg.md`.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-04 — ~50 min — A (`?p=`) + B (`?w=`, masquage jour) + C livrés ; 23 tests verts, e2e OK (semaine décalée). Reste : commit + clôture.
- 2026-07-05 — ~40 min — flèches prev/next en pastilles (style B, chevrons SVG) sur `/weeks` + `/view` ; fix hot-reload docker local (override monte le dossier). 23 tests verts, F-lint OK. Clôturé (commit sur `main`, sans push).
