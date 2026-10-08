# SPEC — suivi-prochaine-facture
Date : 2026-10-08
Statut : terminé (v0.32.0)

## Objectif (une phrase)
Pour une commande, proposer la prochaine facture : les jours exécutés non
facturés ventilés sur les lots, au prorata de ce qui reste à facturer sur
chaque lot du devis.

## Critères de fin (3 max, observables)
- [x] `devis_lots` par commande dans `facturation.yml` (calipso_b et
      calipso_c : WP_1 6 / WP_2 7 / WP_3 7, devis DV20251211 et DV20260627 ;
      speasy : JUICE_E2 60) ; calipso_a, soldée, n'en a pas.
- [x] `/suivi/prochaine` : choix de la commande, nombre de jours pré-rempli
      au reste à facturer arrondi à l'entier inférieur et modifiable,
      ventilation au plus fort reste plafonnée au reste de chaque lot, PU,
      HT, TVA, TTC. calipso_c : 12 j → 4 / 3 / 5, 6 480 € HT.
- [x] Alertes : jours demandés au-delà de l'exécuté non facturé ; jours
      au-delà du devis (non ventilés, à reporter).

## Hors périmètre
- Enregistrer la facture (formulaires de l'étape 3).
- Ventilation par module.
