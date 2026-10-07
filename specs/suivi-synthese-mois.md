# SPEC — suivi-synthese-mois
Date : 2026-10-07
Statut : terminé (v0.25.0)

Deuxième feature du portage de `suivi_chantiers.ods` (cf. `specs/suivi-mois.md`).

## Objectif (une phrase)
Une page `/suivi/synthese` qui reprend le tableau C de la Synthèse : une ligne
par commande, une colonne par mois, le total de jours exécutés.

## Critères de fin (3 max, observables)
- [x] Une ligne par commande (et par projet sans commande, ex. colibri), une
      colonne par mois de la première commande au mois en cours, plus récent à
      gauche comme dans l'ODS, et une colonne total.
- [x] Chaque case égale le total de la commande sur `/suivi?m=…` ; une ligne
      de total par mois.
- [x] Onglets « Mois » / « Synthèse » sur les deux pages ; une case mène à la
      feuille du mois.

## Hors scope — explicitement PAS dans cette feature
- Exécuté / facturé / restant par commande (tableau A) : feature 3.
- Registre des factures (tableau B) : feature 4.

## Budget
- Temps décidé : 1 h (estimation du plan, validée avec le découpage)
- Seuil d'arrêt : budget × 1.5 = 1 h 30

## Plan
| Tâche | Estimation |
|---|---|
| 1. `suivi.py` : `months_between`, `monthly_totals` | 15 min |
| 2. Route `/suivi/synthese` + gabarit + onglets | 25 min |
| 3. Tests | 10 min |
| 4. Vérification : croisement avec le tableau C de l'ODS | 10 min |
| **Total** | **~1 h** |
