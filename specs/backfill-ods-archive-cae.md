# SPEC — backfill-ods-archive-cae
Date : 2026-07-13
Statut : terminé

## Objectif (une phrase)
Importer dans `pomofocus_webhook.csv` les 310 lignes exploitables de
`facturation projets.ods` (archive CAE, ~/00PRO/archives/cae-sapie-2022/), pour
que les vues remontent jusqu'à septembre 2022 et que le trou du CSV se réduise
au 11/04/2025 → 30/09/2025.

## Critères de fin (3 max, observables)
- [x] Le script importe les 310 lignes (266 d'avant mai 2024 + 28 dans le trou),
      sauvegarde le CSV d'abord, ne touche aucun jour déjà présent, et reste
      ré-exécutable (relance = 0 ligne ajoutée).
- [x] Les noms de projets sont normalisés (minuscules, espaces éliminés) de
      sorte que les couleurs et le facturable les traitent correctement.
- [x] `/months?n=120` affiche des barres non nulles sur 2024, et le CSV démarre
      en septembre 2022.

## Hors scope — explicitement PAS dans cette feature
- La période 11/04/2025 → 30/09/2025 : aucun des deux ODS ne la couvre, le trou
  résiduel reste.
- Inventer des heures de début/fin : comme pour `backfill_ods.py`, elles restent
  vides.
- Ajouter les vieux projets (heliopropa, bibheliotech, sapie, iut…) à
  `projects-config.yml` / `BILLABLE_PROJECTS` : couleur par défaut, non
  facturables.
- La colonne `projet_facturé` de l'ODS, qui diffère parfois de `projet/lot` :
  on n'importe que `projet/lot`.

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
**Un second lecteur dans `backfill_ods.py`, pas un second script** : la plomberie
(sauvegarde, `--dry-run`, écriture, et surtout les deux garde-fous `--until` et
« un jour déjà présent n'est jamais touché ») est déjà là et doit être partagée —
c'est elle qui empêche le double comptage avec les jours `bht_dev` du CSV.
Refactor : chaque lecteur renvoie une liste de lignes au schéma CSV, `rows_to_add`
filtre une liste au lieu d'un DataFrame. `--source suivi` (défaut) | `archive`.

Correspondance archive : `date` ← date · `project` ← `projet/lot` normalisé ·
`task` ← `activité` (vide sur 217/400 lignes) · `minutes` ← colonne `minutes` si
renseignée (28 lignes), sinon `nb j × 8 × 60` · heures **vides**.

Normalisation (table d'alias explicite) : `bht2` → `bht` (même projet que
`bht_dev`, périodes qui se chevauchent), `co-libri` → `colibri`, `admin perso` →
`perso_admin`, `admin pro` → `pro_admin` ; le reste en minuscules.

Vérifié en amont : les 14 lignes « en double » n'en sont pas (deux activités le
même jour sur le même projet) → **aucune déduplication**.

| Tâche | Estimation |
|---|---|
| 1. Refactor : lecteurs → liste de lignes CSV | 15 min |
| 2. `read_archive_rows()` + normalisation + `--source` | 20 min |
| 3. Tests (3) | 10 min |
| 4. Vérification sur une copie | 15 min |
| **Total** | **~60 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.
Premier candidat à la coupe : `--source` (un `--ods` seul suffirait).

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-13 : spec + plan validés, exécution lancée.
- 2026-07-14 (~35 min, dans le budget) : `--source archive` livré dans
  `backfill_ods.py` (refactor : les lecteurs renvoient des lignes au schéma CSV,
  `rows_to_add` filtre une liste). 5 tests ajoutés, 69 au vert.
  Vérifié **sur une copie** du CSV, pas sur le fichier réel : 310 lignes
  ajoutées (01/09/2022 → 10/04/2025, 1439,6 h), relance = 0 ligne, lignes
  d'origine intactes, CSV démarrant au 01/09/2022, croisement mois par mois avec
  l'archive sans aucun écart (26 mois), et `/months?n=120` affiche 32 semaines
  non vides sur 2024 (contre rien avant le 28/05 auparavant).
  Écart avec l'estimation de la spec (1466 h) : la colonne `minutes` prime
  désormais sur `nb j × 8` là où elle est renseignée — 1439,6 h est la valeur
  juste. Fusion `bht2` → `bht` effective : 512,8 h d'archive à côté des 137,9 h
  de `bht_dev`, même préfixe donc même couleur.
  **Reste** : application en prod par l'utilisateur (`timer web_sync` → les deux
  backfills → `scp`), hors session de travail.
