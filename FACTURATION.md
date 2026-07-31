# Facturation — de la mesure du temps à la facture

Analyse du 2026-07-31. Point de départ du prochain gros chantier.

Trois documents, trois étages :

| Document | Rôle | Grain |
|---|---|---|
| `pomofocus_webhook.csv` → `/projects` | le temps **mesuré** | 1/4 h |
| `~/00PRO/.../2025-*/administratif_projet/*_LOGS.ods` | le temps **déclaré**, ligne à ligne, contre une commande — **la base de la facture** | 1/2 j |
| `suivi_chantiers.ods`, feuille `Synthèse` | la **synthèse comptable** : commandes, factures, exécuté mensuel | — |

`suivi_chantiers.ods` reste la source de vérité du « reste à facturer », mais
c'est dans les `*_LOGS.ods` que la facture se fabrique.

Constat initial : sur la fenêtre ouverte au 19/06/2026, `/projects` annonce
speasy 4,89 j et calipso 6,27 j, là où l'ODS annonce 3,14 j et 5,91 j.

## En résumé

> ⚠️ Ce qui suit est une **reconstitution** faite en lisant les trois fichiers,
> pas une spécification validée. À confirmer ou corriger avant de coder.

Une facture **ne se calcule pas depuis le timer, elle se rédige**. Le timer dit
combien de jours sont disponibles ; le journal de chantier (`*_LOGS.ods`) dit ce
qu'on déclare, sur quel lot et quelle issue, et dans quelle limite de commande.

Trois niveaux de « jours », à ne jamais confondre : **mesuré** (timer, 1/4 h),
**déclaré** (journal, 1/2 j), **facturé** (tranche ronde). Le « reste à
facturer » de la Synthèse est l'écart entre le premier et le deuxième :
**le stock de jours mesurés pas encore écrits dans le journal**.

Ce que l'outil devrait produire, par commande — c'est l'information de
décision, et elle est aujourd'hui reconstituée à la main :

| | stock mesuré | reste sur la commande | facturable | à reporter |
|---|---|---|---|---|
| speasy | 3,14 j | 33 j | 3,14 j | — |
| calipso_b | 5,91 j | **2 j** | **2 j** (1 080 €) | **3,91 j → `calipso_c`** |

Le blocage pour aller plus loin (générer les lignes de journal elles-mêmes) :
`lot` et `module` sont des catégories client absentes du CSV, et surtout
**`Issue Id` / `Issue name` ne sont plus saisis dans le timer** — le format
`#<id> <nom>: <desc>` existe dans 163 lignes du CSV sur 1511, mais aucune
récente côté speasy.

**À trancher avant tout code** : l'anomalie n° 1 ci-dessous (la 3ᵉ facture
speasy est-elle du 19/06 ou du 29/06 ?), parce qu'elle change le chiffre
affiché aujourd'hui.

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

## Les journaux de chantier — la vraie base de la facture

Deux fichiers, un par client, dans `~/00PRO/co-libri.org-2025/chantiers/` :

- `2025-IESA/administratif_projet/IESA_LOGS.ods`, feuille `IESA_LOGS`
- `2025-Speasy/administratif_projet/SPEASY_LOGS.ods`, feuilles `logs` et `Charge`

C'est **ici** que se fabrique la facture. `suivi_chantiers.ods` n'en est que la
synthèse comptable.

### Structure

| IESA_LOGS | SPEASY_LOGS `logs` |
|---|---|
| `date` (mois en toutes lettres) | `date` (mois) |
| `lot` — système contrôle · mise à jour IHM · tests de validation | `lot` — Juice E2, dev TF |
| `module` — maintenance C1, lees-dispatcher-studio, client hs_logger… | `Issue Id` + `Issue name` — 209 netcdf codec, 183 hapi provider… |
| `description` | `Description` |
| `Projet` — calipso · lees · helioswarm | `Projet` — speasy |
| `jours` | `temps (j)` |
| `PUMA` — la commande et son capital | `PUMA` — idem |
| `à Réaliser (J)` — décompte courant | `RESTE à Réaliser (J)` — idem |
| `Facture`, `Qté (j)`, `HT`, `TTC` | `Num Facture`, `Qté (j)`, `montant ht`, `montant ttc` |

La feuille `Charge` de SPEASY est le **plan de charge par issue** :
`Issue Id, Issue Name, Issue Description, Prévu, Réalisé, Diff`. 60 j prévus,
27 j réalisés, 33 j de reste. Vérifié : le `Réalisé` de chaque issue est
exactement la somme des lignes de `logs` correspondantes, sur les 8 issues
entamées. Cette feuille est tenue à jour, pas décorative.

### Le mécanisme, identique sur les deux chantiers

1. **Une commande ouvre un capital de jours** : `Lot Ferme (13j)`,
   `DV20251211_CL (20j)`, `2680L076888 (60j)`.
2. **Chaque ligne de log consomme ce capital** : un mois, un lot, un
   module ou une issue, une description, un nombre de jours **arrondi au demi-jour**.
3. La colonne « à Réaliser » est le **décompte courant** du capital restant.
4. Quand le cumul consommé depuis la dernière facture atteint une **tranche
   ronde**, la facture est émise : on estampille la dernière ligne du lot avec
   `Num Facture`, `Qté (j)`, `HT`, `TTC`.

Vérifié : aux lignes de facture, le décompte fait
speasy 60 → 51 → 42 → 33 (soit −9, −9, −9) et
IESA 13 → 0 puis 20 → 15 → 10 → 2 (soit −13, −5, −5, −8).
**La quantité facturée est exactement la baisse du décompte entre deux
factures.** Les lignes de log sont donc écrites pour tomber sur une tranche
ronde choisie d'avance.

Conséquence : **une facture ne se calcule pas depuis le timer, elle se rédige.**
Le timer dit combien de jours sont disponibles ; le journal dit ce qu'on
déclare, sur quel lot et quelle issue, et dans quelle limite de commande.

### Trois niveaux de « jours », à ne pas confondre

| Niveau | Source | Grain | speasy | calipso_b |
|---|---|---|---|---|
| **mesuré** | timer → `pomofocus_webhook.csv` → `suivi_chantiers.ods` | 1/4 h | 30,14 j | 23,91 j |
| **déclaré** | `*_LOGS.ods` | 1/2 j | 27 j | 18 j |
| **facturé** | registre / colonne `Facture` | tranche ronde | 27 j | 18 j |

Sur les deux chantiers, **déclaré = facturé** : le journal est écrit jusqu'à la
facture, jamais au-delà.

D'où la lecture juste du « reste à facturer » de la Synthèse :

> **c'est le stock de jours mesurés qui n'ont pas encore été écrits dans le
> journal** — la matière première des prochaines lignes de log.

### Ce que ça donne aujourd'hui

| | stock mesuré | reste sur la commande | facturable maintenant | à reporter |
|---|---|---|---|---|
| speasy | 3,14 j | 33 j | 3,14 j (tranche usuelle : 9 j) | — |
| calipso_b | 5,91 j | **2 j** | **2 j** (1 080 €) | **3,91 j → `calipso_c`** |

C'est exactement le constat de départ : 2 j facturables sur `calipso_b`, le
reste en attente d'une commande `calipso_c`. Le tableau ci-dessus est,
en substance, **la sortie que l'outil devrait produire**.

### Ce qui manque au CSV pour écrire les lignes de log

| Colonne du journal | Disponible dans le CSV ? |
|---|---|
| `date` (mois) | ✅ |
| `jours` | ✅ mesuré, à arrondir au 1/2 j **et** à ajuster pour tomber sur la tranche |
| `description` | ⚠️ la tâche du timer s'en approche (« fix PR », « proto 3: parameter range ») |
| `Projet` (calipso/lees/helioswarm) | ⚠️ le sous-projet CSV est proche (`calipso_lees`) mais pas aligné ; `helioswarm` n'existe pas côté CSV |
| `Issue Id` / `Issue name` | ❌ le format `#<id> <nom>: <desc>` existe dans 163 lignes du CSV sur 1511, mais **aucune** des lignes speasy récentes |
| `lot`, `module` | ❌ catégories côté client, nulle part dans le CSV |
| `PUMA`, capital, décompte | ❌ à configurer |

## Piste pour le chantier

Deux étages, dans cet ordre :

**1. La comptabilité des commandes.** Remplacer dans `projects-config.yml`
`derniere_facture: <date>` par une liste de **commandes** : référence PUMA,
TJM, capital en jours, cumul déjà facturé. `/projects` afficherait alors, par
commande : stock mesuré, reste sur la commande, facturable maintenant, à
reporter sur une commande suivante. Cela suffit déjà à produire le tableau
« Ce que ça donne aujourd'hui » ci-dessus, qui est l'information de décision.

**2. Le brouillon de lignes de journal.** Générer depuis le CSV, pour la
période à facturer, des lignes pré-remplies (mois, sous-projet, description =
tâche, jours arrondis au 1/2 j), à compléter à la main pour `lot`, `module` /
`Issue Id`, puis à coller dans le `*_LOGS.ods`. L'outil ne peut pas décider du
lot ni de l'issue — il peut faire toute la comptabilité autour.

Points à trancher avant de coder :

- La config YAML suffit-elle, ou faut-il lire les ODS directement ? Le
  conteneur webhook n'a volontairement ni pandas ni odfpy
  (cf. `specs/backfill-ods-webhook-csv.md`).
- Faut-il rétablir la discipline `#<issue_id> <issue_name>: <description>` dans
  le timer pour speasy ? C'est ce qui rendrait l'étage 2 réellement automatique
  — et ça alimenterait aussi la feuille `Charge`.
- `calipso_a` / `calipso_b` / `calipso_c` sont des **commandes**, alors que
  `calipso_iesa` / `calipso_lees` sont des **lots techniques**. Les deux axes
  coexistent ; le détail par sous-projet livré en v0.14.0 ne suit que le second.

## Anomalies relevées dans les trois fichiers

1. **Numéro de la 3ᵉ facture speasy** : `FA20260629` dans SPEASY_LOGS, mais
   `FA20260619` daté du 19/06 dans la Synthèse, et `derniere_facture:
   "20260619"` dans `projects-config.yml`. Dix jours d'écart. Si le 29/06 est
   le bon, `/projects` sur-compte speasy de 1,32 j (4,89 → 3,57 j).
2. **Facture IESA** : id `FA20260618` dans les deux fichiers, mais datée du
   19/06 dans la Synthèse.
3. **Colonne `PUMA` de SPEASY_LOGS corrompue** : la référence s'incrémente
   ligne après ligne — 2680L076888, 2681L…, 2682L…, jusqu'à 2691L076888.
   Recopie tirée à la souris. La bonne référence est `2680L076888`, confirmée
   par la Synthèse. C'est une référence client, elle mérite d'être corrigée.
4. **Deux définitions de « reste à réaliser »** : 33 j dans SPEASY_LOGS
   (60 − déclaré) contre 29,86 j dans la Synthèse (60 − mesuré). L'écart de
   3,14 j est précisément le « reste à facturer ».
5. **IESA_LOGS ligne 7** : module `iesa-dispatcher-studio` mais colonne
   `Projet` à `lees` — probable recopie de la ligne précédente.
6. **IESA_LOGS ligne 36** : un `5,5` isolé dans la colonne `jours`, très en
   dessous des données. Résidu de calcul.
7. **`carangues`** : présent dans le CSV en avril, juin et juillet, mais le
   tableau C de la Synthèse ne lui connaît que `fev_26`.

## Reproduire l'analyse

```bash
workon time_tracking && python - <<'EOF'
import pandas as pd
import webhook_receiver as w

CH = '/home/richard/00PRO/co-libri.org-2025/chantiers'
ods = pd.read_excel('suivi_chantiers.ods', sheet_name='Synthèse',
                    engine='odf', header=None)
print(ods.iloc[0:9, 0:22].to_string())    # tableaux A et B
print(ods.iloc[36:42, 0:12].to_string())  # tableau C

for path, sheet in ((f'{CH}/2025-IESA/administratif_projet/IESA_LOGS.ods', 'IESA_LOGS'),
                    (f'{CH}/2025-Speasy/administratif_projet/SPEASY_LOGS.ods', 'logs')):
    print(pd.read_excel(path, sheet_name=sheet, engine='odf',
                        header=0).dropna(how='all').to_string())

rows = w._read_csv_rows('webhook-data/pomofocus_webhook.csv')
for p in ('speasy', 'calipso'):
    m = w.project_minutes_since(rows, p, '20260619', quantize=True)
    print(p, m / 60 / 8, 'j depuis le 19/06 (arrondi 1/4 h)')
EOF
```
