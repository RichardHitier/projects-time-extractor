# SPEC — facturation-emettre
Date : 2026-10-08
Statut : terminé (v0.38.0)

Étape 2a du workflow (`FACTURATION-CHANTIER.md` §3) : enregistrer la facture
dès son émission.

## Objectif (une phrase)
Un formulaire « Émettre » sur `/facturation`, pré-rempli par la ventilation
proposée, qui ajoute la facture au `facturation.yml` du serveur.

## Critères de fin (3 max, observables)
- [x] Formulaire pré-rempli : n° `FA<aaaammjj>` du jour, date du jour, jours
      et lots proposés, modifiables.
- [x] Refus sans écriture si : n° mal formé ou déjà pris, date invalide,
      commande inconnue, lot hors devis, somme des lots ≠ jours.
- [x] Écriture = une ligne ajoutée en fin de `factures:` (commentaires et mise
      en forme intacts), sauvegarde dans `DATA/bckp/` avant, relecture après
      (restauration si illisible) ; message « FA… enregistrée ».

## Hors périmètre
- « payée le », trimestre de TVA, « déclarée le » (étapes 3 et 4).
- Brouillon du journal `*_LOGS.ods` (étape 2b).
