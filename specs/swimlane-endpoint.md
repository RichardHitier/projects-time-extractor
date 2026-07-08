# SPEC — swimlane-endpoint
Date : 2026-07-08
Statut : terminé

## Objectif (une phrase)
Depuis l'appli webhook, consulter à l'URL `/swimlane` une frise Gantt des 10
derniers jours (une ligne par jour, plus récent en haut), avec des barres
colorées par projet positionnées selon l'heure de la journée.

## Critères de fin (3 max, observables)
- [x] `/swimlane` (et `/<secret>/swimlane`) renvoie une page HTML au thème sombre
      de l'appli, avec une frise SVG des 10 derniers jours, plus récent en haut.
- [x] Chaque barre est colorée par projet (mêmes couleurs que `/activity`, via
      `project_color`) et positionnée selon l'heure début/fin ; les jours sans
      activité restent des lignes vides.
- [x] Une barre de menu (live / weeks / swimlane) en haut de chaque page permet
      de naviguer de l'une à l'autre.

## Hors scope — explicitement PAS dans cette feature
- Navigation temporelle sur `/swimlane` (prev/next, `?w=`) — fenêtre figée à 10 jours.
- Fenêtre paramétrable (`/swimlane/30`, sélecteur de nombre de jours).
- Filtrage par projet.
- Auto-refresh live du swimlane (poll toutes les 3 s comme `/view`).
- Toucher au `timer swimlane` du CLI (matplotlib) — on ne modifie que le web.

## Budget
- Temps décidé : 1 h 30  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 2 h 15
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
| Tâche | Estimation |
|---|---|
| A — helper `swimlane_days(rows, last_day, n=10)` | 15 min |
| B — `render_swimlane_svg(days)` (frise SVG) | 35 min |
| C — route `/swimlane` + template `SWIMLANE_HTML` | 15 min |
| D — barre de menu partagée (live/weeks/swimlane) sur les 3 pages | 15 min |
| E — vérif manuelle + journal | 10 min |
| **Total** | **1 h 30** |

→ Si Total > Budget : couper du scope ICI, avant de coder.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-08, ~1 h : implémenté `swimlane_days` + `render_swimlane_svg` + route
  `/swimlane` + menu partagé (live/weeks/swimlane). 3 critères OK, vérif manuelle
  (test client + rendu PNG sur pomofocus.csv, secret gating). Reste : commit.
