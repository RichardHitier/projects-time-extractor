# SPEC — web-sync-facturation
Date : 2026-10-08
Statut : terminé (v0.30.0)

Premier morceau de l'étape 3 de `plan_suite.md` (saisie dans l'appli) : la
prod devient la référence de `facturation.yml`.

## Objectif (une phrase)
`timer web-sync` rapatrie `facturation.yml` de la prod à côté du CSV, comme il
rapatrie déjà `pomofocus_webhook.csv`.

## Critères de fin (3 max, observables)
- [x] `GET /api/facturation` sert le fichier tel quel (404 s'il manque).
- [x] `timer web-sync` écrit `webhook-data/facturation.yml` ; URL et nom dans
      `config.yml` (`WEBHOOK_FACTURATION_URL`, `WEBHOOK_FACTURATION_FILENAME`).
- [x] Garde-fous : contenu reçu non YAML ou sans `commandes` → rien écrasé ;
      fichier local différent → sauvegardé horodaté dans `DATA/bckp/`.

## Hors périmètre
- Protection des routes : `/api/facturation` est aussi public que `/api/csv`
  et `/suivi`. À traiter avant les formulaires d'écriture.
