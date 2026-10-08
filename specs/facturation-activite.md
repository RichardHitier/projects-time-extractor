# SPEC — facturation-activite
Date : 2026-10-08
Statut : terminé (v0.34.0)

## Objectif (une phrase)
Un rapport d'activité par commande : les jours ventilés par module
(sous-projet du CSV : iesa / lees pour calipso) et par mois, pour préparer
les futures factures.

## Critères de fin (3 max, observables)
- [x] `/facturation/activite?c=` : une ligne par module (part en %), Total,
      mois avec activité seulement, le plus récent à gauche ; ligne
      `ajustements` à part (masquée si nulle).
- [x] Mêmes séances et même arrondi que la Synthèse : le total d'une commande
      = son exécuté (`suivi.module_totals` réutilise `month_lines`).
- [x] Onglets « Prochaine facture » / « Activité » sur `/facturation`.

## Hors périmètre
- Période « facture à venir » (quelles séances restent à facturer) : à
  définir avec les rapports manuels.
- Ventilation speasy par issue.
