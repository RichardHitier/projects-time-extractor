# SPEC — suivi-factures
Date : 2026-10-07
Statut : terminé (v0.28.0)

Quatrième et dernière feature du portage de `suivi_chantiers.ods`.

## Objectif (une phrase)
Une page `/suivi/factures` qui reprend le tableau B de la Synthèse : le
registre des factures avec émission, paiement et déclaration de TVA.

## Critères de fin (3 max, observables)
- [x] Une ligne par facture de `facturation.yml`, par date d'émission : n°,
      commande, jours, TJM, HT, TVA (20 %), TTC, payée le, trimestre de TVA,
      déclarée le ; total jours / HT / TVA / TTC. Montants = ODS.
- [x] TVA sur les encaissements : trimestre = celui du paiement, date de
      déclaration lue dans `tva_declarations` ; « impayée » et « à déclarer »
      mis en évidence.
- [x] Tableau « TVA par trimestre » (factures, HT encaissé, TVA, déclarée le) ;
      onglet « Factures » à côté de Mois / Synthèse.

## Hors scope
- Saisie d'une facture depuis l'appli (formulaires, plus tard).
- Édition / génération de la facture elle-même (D4).

## Budget
- Temps décidé : 1 h (estimation du plan)
