# SPEC — suivi-mois
Date : 2026-10-07
Statut : terminé (v0.24.0)

Première feature du portage de `suivi_chantiers.ods` dans l'appli web (feuilles
mois → sommes par commande et par mois → exécuté / facturé / restant → registre
des factures). Remplace à terme `timer ods-sync` ; la feuille `eighty-hours`
n'est pas portée (plus utile).

## Objectif (une phrase)
Une page `/suivi?m=YYYYMM` qui affiche la feuille d'un mois comme l'ODS
(DATE · COMMANDE · SS-PROJET · DESCRIPTION · JOURS), calculée en direct depuis
`pomofocus_webhook.csv`, chaque séance rattachée à sa commande par date.

## Critères de fin (3 max, observables)
- [x] `/suivi?m=202609` affiche les lignes de septembre 2026 avec un total par
      commande égal à la feuille `sep_26` de l'ODS (calipso_c 9,00 j,
      speasy 3,28 j, colibri 0,31 j).
- [x] Une séance `calipso_*` est rattachée à calipso_a / calipso_b / calipso_c
      selon les dates `debut` de `webhook-data/facturation.yml` (décembre 2025 :
      calipso_a jusqu'au 04/12, calipso_b ensuite).
- [x] Navigation ‹ mois › et entrée « Suivi » dans le menu.

## Résultat
Croisement avec l'ODS, mois par mois : oct. 2025, janv., juin, août, sept. et
oct. 2026 identiques ; la commande est la bonne partout. Écarts restants =
mois retouchés à la main dans l'ODS (nov./déc. 2025, fév. → mai 2026, juil.
2026 à 0,06 j) → correction du CSV, hors scope.

## Hors scope — explicitement PAS dans cette feature
- Correction du CSV pour les mois où l'ODS a été retouché (nov./déc. 2025,
  fév. → mai 2026) : opération de données à part, pull → correction → push.
- Sommes par mois (tableau C), exécuté / facturé / restant (tableau A),
  registre des factures (tableau B) : features suivantes.
- Formulaires de saisie, lot / module, remplacement de `/projects`.

## Données
`webhook-data/facturation.yml` (volume Docker, hors git) : `commandes`
(nom, projet, ref, tjm, devis, debut), `factures`, `tva_declarations`.

## Budget
- Temps décidé : 2 h  (décidé AVANT le code)
- Seuil d'arrêt : budget × 1.5 = 3 h
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan
| Tâche | Estimation |
|---|---|
| 1. `facturation.yml` | fait |
| 2. `suivi.py` : chargement YAML, commande d'une séance, lignes d'un mois | 45 min |
| 3. Route `/suivi` + `SUIVI_HTML` + menu + `Dockerfile` | 40 min |
| 4. Tests (`tests/test_suivi.py`) | 20 min |
| 5. Vérification : croisement avec les feuilles de l'ODS | 15 min |
| **Total** | **~2 h** |
