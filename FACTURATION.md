# Facturation — `suivi_chantiers.ods` vs `/projects`

Analyse du 2026-07-31. Point de départ du prochain gros chantier : faire dire à
`/projects` la même chose qu'à l'ODS, qui reste la **source de vérité** du
« reste à facturer ».

Constat initial : sur la fenêtre ouverte au 19/06/2026, `/projects` annonce
speasy 4,89 j et calipso 6,27 j, là où l'ODS annonce 3,14 j et 5,91 j.

## La feuille `Synthèse` de `suivi_chantiers.ods`

Trois tableaux dans une seule feuille (lus sans en-tête : `pd.read_excel(...,
sheet_name='Synthèse', header=None)`).

### A — une ligne par *commande*, pas par projet (lignes 2-4)

| Commande | N° | TJM | Devis | Exécuté | Facturé | Reste à facturer | Reste à réaliser |
|---|---|---|---|---|---|---|---|
| calipso_a | 2680L076892 | 540 | 13 j | 13 | 13 | 0 | 0 |
| speasy | 2680L076888 | 490 | 60 j | 30,1425 | 27 | **3,1425 j** (1 540 €) | 29,86 j |
| calipso_b | 2680L077378 | 540 | 20 j | 23,911 | 18 | **5,911 j** (3 192 €) | **−3,911 j** |

Colonnes : `Projet, Commande, TJM, Devis (jours, HT), exécuté (j), facturé (j),
reste à facturer (jours, HT), reste à réaliser (jours, HT)`.

### B — le registre des factures (colonnes 12-21)

`date, Lot facturé, nb jour, tjm, montant ht, ttc, id facture, payée, TVA, déclarée`

| Date | Lot | Jours | Facture | Payée |
|---|---|---|---|---|
| 2025-11-18 | calipso_a | 13 | FA20251118 | 2025-12-16 |
| 2025-12-19 | calipso_b | 5 | FA20251219 | 2026-01-21 |
| 2026-01-27 | calipso_b | 5 | FA20260127 | 2026-02-09 |
| 2026-01-29 | speasy | 9 | FA20260129 | 2026-02-23 |
| 2026-04-01 | speasy | 9 | FA20260401 | 2026-04-21 |
| 2026-06-19 | speasy | 9 | FA20260619 | — |
| 2026-06-19 | calipso_b | 8 | FA20260618 | — |

speasy = 9+9+9 = 27 j facturés ; calipso_b = 5+5+8 = 18 j.
(Incohérence mineure : la dernière ligne est datée du 19/06 mais porte l'id
`FA20260618`.)

### C — l'exécuté par projet et par mois (lignes 36-41)

`projet, total, juil_26 … oct_25`, une ligne par projet, `calipso_a` et
`calipso_b` séparés.

## L'écart : une définition, pas une donnée manquante

- **ODS** : `reste à facturer = cumul exécuté − cumul facturé`, depuis le début
  de la commande.
- **`/projects`** : temps saisi **après la date** de la dernière facture
  (`derniere_facture` dans `projects-config.yml`).

Les deux ne coïncident que si chaque facture a porté exactement le réalisé du
jour de son émission. Or les factures portent des **nombres ronds** — 13, 5, 5,
9, 9, 9, 8 jours. L'écart est l'avance accumulée :

| | réalisé au 19/06 | facturé | avance | reste ODS | `/projects` |
|---|---|---|---|---|---|
| speasy | 24,89 j | 27 j | **+2,11 j** | 3,14 j | 5,25 j |
| calipso_b | 17,38 j | 18 j | **+0,62 j** | 5,91 j | 6,53 j |

**Des jours ont été facturés avant d'être réalisés.** `/projects` ne peut pas le
savoir : il ne connaît qu'une date, pas un nombre de jours facturés.

⚠️ Ces chiffres sont **arrondis au quart d'heure**, comme l'ODS. Les 4,89 et
6,27 constatés au départ viennent de `/projects` sans l'arrondi : le bouton
« 1/4 h » doit être coché pour comparer les mêmes grandeurs. Cela vaut 0,36 j
sur speasy à lui seul.

## Ce que `/projects` ignore, par ordre d'importance

1. **La notion de commande.** L'ODS suit `calipso_a` (13 j, soldée) et
   `calipso_b` (20 j) comme deux lignes distinctes avec leur n° de bon. Le CSV
   ne connaît que `calipso_iesa` / `calipso_lees` — des **lots techniques**, pas
   des commandes. Le détail par sous-projet livré en v0.14.0 découpe donc selon
   un axe qui n'est pas celui de la facturation.
2. **Le nombre de jours déjà facturés.** C'est la vraie donnée manquante dans
   `projects-config.yml` : il n'y a que `derniere_facture` (une date), alors que
   l'ODS raisonne en cumul.
3. **Le devis, donc le dépassement.** calipso_b : 20 j commandés, 23,91
   exécutés → « reste à réaliser −3,911 j ». `/projects` annonce « 6,53 j à
   facturer » sans dire qu'une partie n'a aucune commande pour la porter.
4. **Le registre des factures** : id, payée, TVA, déclarée. Deux factures du
   19/06 sont encore impayées.

## calipso_b → calipso_c

20 j commandés − 18 facturés = **2 j encore facturables sur `calipso_b`**.
Les 3,911 j restants (5,911 − 2) sont réalisés hors commande et attendent une
commande **`calipso_c`**. C'est ce que dit la colonne « reste à réaliser » à
−3,911.

## Vérification : l'ODS est bien une vue du CSV

Arrondi au quart d'heure, `juin_26` et `juil_26` tombent à la 4ᵉ décimale près :
speasy 2,75 / 3,8438 · calipso_b 8,2188 / 4,5625 · colibri 3,5938 / 2,5625.
**Aucune perte de donnée depuis le 19/06** : l'écart constaté n'est pas un
problème de données.

Sur l'ensemble oct_25 → juil_26 en revanche (CSV − ODS) :

| Projet | CSV | ODS | Écart |
|---|---|---|---|
| speasy | 30,0000 | 30,1425 | −0,14 |
| calipso (a+b) | 34,8750 | 36,8237 | **−1,95** |
| colibri | 20,2188 | 19,8200 | +0,40 |
| carangues | 2,0000 | 0,5625 | **+1,44** |

- calipso : l'écart tient presque entièrement à `nov_25` (CSV 4,31 vs ODS 6,41).
- carangues : la ligne du tableau C n'a que `fev_26`, alors que le CSV a de
  l'activité en avril, juin et juillet — le tableau C est en retard sur ce
  projet.
- speasy et colibri : des mois qui divergent (fév→mai) puis se compensent ;
  cohérent avec l'écart déjà documenté entre `pomofocus.csv` et le webhook
  (TODO.md item 1).

Rien de tout cela n'affecte le delta courant, mais c'est à regarder à part.

## Piste pour le chantier

Remplacer, dans `projects-config.yml`, `derniere_facture: <date>` par la notion
de **commande** : n° de bon, TJM, devis en jours, et **cumul des jours
facturés**. Découper `calipso` en `calipso_b` / `calipso_c`. `/projects`
calculerait alors `exécuté − facturé` comme l'ODS, et pourrait afficher le
dépassement de devis.

Question ouverte : la config YAML suffit-elle, ou faut-il lire le registre des
factures (tableau B) directement, au risque de dépendre de l'ODS depuis le
conteneur webhook — qui n'a volontairement ni pandas ni odfpy (cf.
`specs/backfill-ods-webhook-csv.md`) ?

## Reproduire l'analyse

```bash
workon time_tracking && python - <<'EOF'
import pandas as pd
import webhook_receiver as w
ods = pd.read_excel('suivi_chantiers.ods', sheet_name='Synthèse',
                    engine='odf', header=None)
print(ods.iloc[0:9, 0:22].to_string())    # tableaux A et B
print(ods.iloc[36:42, 0:12].to_string())  # tableau C
rows = w._read_csv_rows('webhook-data/pomofocus_webhook.csv')
for p in ('speasy', 'calipso'):
    m = w.project_minutes_since(rows, p, '20260619', quantize=True)
    print(p, m / 60 / 8, 'j depuis le 19/06 (arrondi 1/4 h)')
EOF
```
