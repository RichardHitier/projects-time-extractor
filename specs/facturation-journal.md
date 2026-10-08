# SPEC — facturation-journal
Date : 2026-10-08
Statut : terminé (v0.40.0)

Étape 2b du workflow (`FACTURATION-CHANTIER.md` §3) ; tient aussi lieu de
rapport d'activité par facture.

## Objectif (une phrase)
Pour une facture émise, un brouillon des lignes de journal (`*_LOGS.ods`) à
copier-coller : mois, lot, module/issue, jours au 1/2 j, décompte,
estampille.

## Critères de fin (3 max, observables)
- [x] Séances de la commande entre la facture précédente (exclue ; sinon le
      début de la commande) et la date de la facture, une ligne par (mois,
      sous-projet, tâche) ; jours de la facture au prorata, en demi-journées,
      somme exacte ; lots remplis dans l'ordre, ligne coupée si besoin.
- [x] Colonnes du journal du projet (IESA_LOGS pour calipso, SPEASY_LOGS
      `logs` pour speasy), reste à réaliser, estampille n°/qté/HT/TTC.
- [x] `/facturation/journal?f=` : aperçu + texte tabulé + « copier » ; liens
      depuis « Émettre » et le registre des factures.

## Limites connues
- Brouillon : lot et commande se décident à la main (ex. « June Tiny Fixes »
  rattaché par date à calipso_c, facturé en réalité sur calipso_b).
- `description` (IESA) et `Issue Id` (speasy) restent à remplir.
