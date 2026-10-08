# SPEC — suivi-total-live
Date : 2026-10-08
Statut : terminé (v0.29.0)

Étape 2 de `plan_suite.md` : le dernier chiffre faux de l'appli.

## Objectif (une phrase)
Le « à facturer » de `/live` (et `/api/rows`) devient le total « Reste à
facturer HT » de `/suivi/synthese`, fixe quel que soit le sélecteur d'arrondi.

## Critères de fin (3 max, observables)
- [x] `/live`, `/api/rows` et le Total HT de `/suivi/synthese` affichent le
      même montant ; changer le sélecteur ne le change pas.
- [x] Le pas d'arrondi facturable vit dans `config.yml`
      (`BILLING_ROUND_MINUTES: 15`) ; le sélecteur de `/live` n'offre plus que
      brut / 15'.
- [x] Jours à 2 décimales sur `/suivi` (Mois, Synthèse) ; jour entier conservé
      sur Factures.

## Hors périmètre
- `/projects` reste tel quel (détail par sous-projet, `derniere_facture`)
  tant que ce détail n'a pas d'autre page : sa suppression attend.
