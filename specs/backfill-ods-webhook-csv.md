# SPEC — backfill-ods-webhook-csv
Date : 2026-07-13
Statut : terminé

## Objectif (une phrase)
Un script de backfill hors ligne qui injecte dans `pomofocus_webhook.csv` les
lignes de `suivi_chantiers.ods` couvrant le trou du CSV (oct. 2025 → 18/02/2026),
de sorte que `/live`, `/weeks` et `/months` affichent cette période.

## Critères de fin (3 max, observables)
- [x] Le script sauvegarde le CSV avant écriture, puis y ajoute les ~70 lignes
      de l'ODS antérieures au 19/02/2026 — sans toucher aux lignes existantes
      ni créer de doublon.
- [x] `/months?n=120` affiche des barres non nulles d'octobre 2025 à
      février 2026.
- [x] Les totaux facturables de ces semaines correspondent aux `JOURS × 8 h`
      de l'ODS.

## Hors scope — explicitement PAS dans cette feature
- La période mars → septembre 2025 : l'ODS n'a aucune feuille avant `oct_25`,
  elle reste un trou.
- Inventer des heures de début/fin : les lignes importées les laissent vides.
- Toute synchronisation continue ODS → CSV : c'est un one-shot, pas un import
  récurrent.
- Lire l'ODS depuis le conteneur webhook (pas de pandas dedans, volontairement).

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
Script autonome `backfill_ods.py` à la racine, sur le modèle de
`webhook_log_to_csv.py` (convertisseur one-shot vers le schéma CSV, lit
`config.py`, n'importe pas `webhook_receiver`). pandas + odfpy ne sont pas dans
le conteneur webhook → exécution côté CLI uniquement.

**Cible = la prod** : `webhook-data/pomofocus_webhook.csv` en local n'est qu'un
miroir (`cmd_web_sync`, cli.py:217, le réécrit depuis timer.co-libri.org). La
séquence est **pull → backfill → push (scp par l'utilisateur)**.

Correspondance : `date` ← DATE (%Y%m%d) · `project` ← PROJET (avant le `_`) + `_`
+ SS-PROJET (`calipso_b`/`iesa` → `calipso_iesa`) · `task` ← DESCRIPTION ·
`minutes` ← JOURS × 8 × 60 · `startTime`/`endTime` **vides** (l'ODS n'a pas
d'heures ; les inventer est hors scope).

Deux garde-fous contre les doublons : `--until 20260218` (au-delà, le CSV est la
source de vérité) et **un jour déjà présent dans le CSV n'est jamais touché**
(script ré-exécutable).

| Tâche | Estimation |
|---|---|
| 1. `backfill_ods.py` : lecture ODS, mapping, écriture CSV | 25 min |
| 2. Garde-fous : `--until`, jours déjà présents, `--dry-run`, sauvegarde `.bak` | 15 min |
| 3. Tests (mapping + idempotence) | 10 min |
| 4. Vérification locale | 10 min |
| **Total** | **~60 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.
Premier candidat à la coupe : `--dry-run` (le `--csv` sur une copie suffit).

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-13 : spec + plan validés, exécution lancée.
- 2026-07-13 (~40 min, dans le budget) : `backfill_ods.py` livré (+ 4 tests,
  61 au vert). Vérifié **sur une copie** du CSV, pas sur le fichier réel :
  70 lignes ajoutées (01/10/2025 → 18/02/2026, 36,70 j / 293,6 h), relance =
  0 ligne (idempotent), `/months?n=120` montre 15 semaines non vides sur la
  période, et les totaux facturables croisés avec l'ODS tombent au centième
  près (238,60 h des deux côtés, 47 jours, aucun écart).
  **Reste** : l'application réelle est pilotée par l'utilisateur —
  `timer web_sync` (pull prod) → `python backfill_ods.py` → `scp` vers le VPS,
  hors session de travail (une ligne écrite en prod entre le pull et le push
  serait écrasée).
