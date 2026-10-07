# SPEC — suivi-commandes
Date : 2026-10-07
Statut : terminé (v0.27.0)

Troisième feature du portage de `suivi_chantiers.ods` (cf. `specs/suivi-mois.md`,
`specs/suivi-synthese-mois.md`, `specs/suivi-ajustements.md`).

## Objectif (une phrase)
En haut de `/suivi/synthese`, le tableau A de la Synthèse : par commande, TJM,
devis, exécuté, facturé, reste à facturer (jours et € HT), reste à réaliser.

## Critères de fin (3 max, observables)
- [x] Une ligne par commande de `facturation.yml` ; facturé = somme des
      `factures` de la commande ; exécuté = total de la commande sur
      `/suivi/synthese`, ajustements compris.
- [x] Reste à facturer et reste à réaliser négatifs en évidence (facturé
      d'avance, dépassement de commande) ; total du reste à facturer en € HT.
- [x] Chiffres = ODS : speasy 3,23625 j / 1 586 € ; calipso_b −0,65125 j /
      −352 €. Écarts voulus : calipso_a −0,0875 j (l'ODS affiche 13 exécutés
      en dur, ses feuilles en contiennent 12,9125) ; calipso_c +0,0625 j
      (31/07, le CSV a raison).

## Hors scope
- Registre des factures (tableau B) : feature 4.
- Remplacement de `/projects`.

## Budget
- Temps décidé : 1 h 30 (estimation du plan)
