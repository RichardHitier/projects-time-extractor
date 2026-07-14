# SPEC — months-pagination
Date : 2026-07-14
Statut : en cours

## Objectif (une phrase)
Sur `/months`, remonter jusqu'au début des données (sept. 2022) : plafond de
`?n=` porté à 200 semaines, et pagination `?p=` par tranches, avec des boutons
de navigation entre les tranches.

## Critères de fin (3 max, observables)
- [x] `/months` sans paramètre affiche **60 semaines** ; `?n=` accepte jusqu'à
      **200** (au-delà, plafonné).
- [x] `?p=N` recule de N × n semaines : avec le défaut, `?p=3` atteint l'automne
      2022, début des données. (Corrigé en mode plan : les données commencent
      201 semaines en arrière, donc p=3 — pas p=2 comme écrit initialement.)
- [x] Des boutons « plus anciennes / plus récentes » naviguent entre les
      tranches et se désactivent aux bornes, comme sur `/weeks`.

## Hors scope — explicitement PAS dans cette feature
- Le saut direct à une date (« aller à janvier 2024 » d'un coup).
- La borne haute automatique : la navigation s'arrête aux 200 semaines, pas à
  la fin des données.
- Le défilement infini.
- Tout changement du rendu des graphes (étiquettes, barres, couleurs).

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
Idée directrice : **transposer la pagination de `/weeks`**. `recent_weeks`
(webhook_receiver.py:351) sait déjà reculer son lundi de départ de `page × count`
semaines ; on applique la même chose à `recent_week_totals`, son équivalent
« une ligne = une semaine ». Rien à changer dans les renderers.

Bornage : `p = min(p, MONTH_MAX_WEEKS // n)` — la fenêtre ne démarre jamais plus
de 200 semaines en arrière. Avec n=60, `p_max = 3`, ce qui suffit exactement à
atteindre sept. 2022 (fenêtre p=3 : 13/12/2021 → 05/02/2023).

| Tâche | Estimation |
|---|---|
| 1. `recent_week_totals(page=0)` + constantes (défaut 60, max 200) | 10 min |
| 2. Route : `?p=`, bornage, boutons désactivés aux bornes | 15 min |
| 3. Titre : la période affichée, pas « les N dernières » | 5 min |
| 4. Tests (3) | 15 min |
| 5. Vérification | 10 min |
| **Total** | **~55 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.
Premier candidat à la coupe : le titre (étape 3).

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-14 : spec + plan validés, exécution lancée.
- 2026-07-14 (~35 min, dans le budget) : livré. `recent_week_totals(page=)`
  transpose la pagination de `recent_weeks` ; route bornée par
  `min(p, MONTH_MAX_WEEKS // n)` ; deuxième ligne de nav (« plus récentes / plus
  anciennes », grisées aux bornes) ; le réglage de `n` propage `p` ; titre et
  `<title>` nomment la fenêtre (« 60 semaines, décembre 2021 → février 2023 »)
  au lieu de « les N dernières ». 3 tests (72 au vert).
  Vérifié sur les vraies données : p=0→3 couvrent mai 2025→juil. 2026, avril
  2024→mai 2025, févr. 2023→mars 2024, déc. 2021→févr. 2023 ; p=4 est ramené à
  p=3 avec le bouton grisé ; et les totaux facturables de trois semaines
  d'automne 2022 (20 h, 4 h, 28 h) sont identiques à ceux de `/weeks?p=16`.
  Reste : contrôle visuel après `docker compose restart webhook`.
