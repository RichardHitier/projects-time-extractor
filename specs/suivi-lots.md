# SPEC — suivi-lots
Date : 2026-10-08
Statut : terminé (v0.31.0)

## Objectif (une phrase)
Une base qui contient, pour chaque facture émise, la ventilation des jours
facturés par lot client, et un onglet `/suivi/lots` pour la visualiser.

## Critères de fin (3 max, observables)
- [x] `facturation.yml` : catalogue `lots` par projet (code → libellé) et
      `lots: {code: jours}` sur chaque facture, remplis depuis les `FA*.odt`
      (`dev/extract_lots_odt.py`, script jetable). Codes : désignation avant
      « : », espaces → `_` (`WP_1`, `JUICE_E2`).
- [x] `/suivi/lots` : un tableau par projet, une ligne par facture, une
      colonne par lot (libellé au survol), sous-total par commande, total.
- [x] Facture non ventilée, ou dont les lots ne font pas ses jours, signalée.

## Hors périmètre
- Ventilation par **module** : même mécanique, catalogue à part (à venir).
- Saisie des lots dans l'appli (formulaires de l'étape 3).
