# Reste à faire avant la v1.0.0

État au 2026-10-16 (v0.51.0). Jalon défini dans `plan_suite.md` :

> **v1.0.0 = plus besoin de `suivi_chantiers.ods` ni d'éditer
> `facturation.yml` à la main** — le cycle complet d'une facture se fait
> dans l'outil.

## Fait

- [x] Temps à facturer → facture créée (`/facturation`, « Émettre », v0.38.0).

## Reste — 4 cases sur 5

1. [ ] **Documents FA + BL générés** — commande `timer facture FA…`
   (`plan_generation_facture.md`, points 1-4). L'essai
   `dev/gen_facture_odt.py` existe (BL compris depuis le 2026-10-12). Reste :
   - un modèle `.odt` de référence par client ;
   - vérifier le cas speasy (`FA20260805.odt`, un seul lot) ;
   - rendre générique (ne plus dépendre du style `T10` ni des noms de champs) ;
   - la vraie commande CLI, lisant `facturation.yml`.
2. [ ] **États de la facture dans l'appli** (`plan_generation_facture.md`,
   point 11) — aucun formulaire n'existe (seuls POST de /facturation :
   « Émettre » et « Supprimer ») :
   - déposée (Chorus + mail) ;
   - payée le, trimestre de TVA pré-rempli d'après la date ;
   - TVA déclarée le, par trimestre.
3. [ ] **Corriger une facture** — la suppression existe (v0.46.0, impayées
   seulement), pas la correction.
4. [ ] **Nouvelle commande (devis)** — nom, projet, réf. PUMA, `devis_ref`,
   TJM, jours au devis, début, jours par lot.
5. [ ] **ODS retiré de la CLI** — `ods-sync`, `report --view ods`,
   `eighty-hours`, `dev/add_month_sheets.py`. La preuve qu'on n'en a plus
   besoin.

Le plus gros morceau : le point 1 (génération des documents).

## À noter

- Les livraisons v0.47 → v0.51 (projet extern / `not_working_time`, ajout de
  ligne dans /rows, infobulles swimlane) sont hors du chemin v1.
- `plan_suite.md` date du 2026-10-08 (v0.43.0) : il ne mentionne ni la
  suppression de facture (v0.46.0) ni les commandes soldées hors total
  (v0.45.0), cochées seulement dans `plan_generation_facture.md`.
