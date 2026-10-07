# SPEC — suivi-ajustements
Date : 2026-10-07
Statut : terminé (v0.26.0)

Portage de `suivi_chantiers.ods`, avant le tableau des commandes (feature 3).

## Objectif (une phrase)
Aligner les jours retenus pour la facturation sur l'ODS (mois facturés, figés)
sans réécrire `pomofocus_webhook.csv`, par des ajustements par commande et par
mois déclarés dans `facturation.yml`.

## Pourquoi pas une correction du CSV
Comparaison jour par jour ODS ↔ CSV : fév. → mai 2026, l'ODS porte des valeurs
saisies à la main (~90 jours) là où le CSV a les vraies séances avec leurs
heures ; les remplacer aurait effacé ces données pour /weeks, /live, /swimlane.
En nov. 2025, 4 jours de calipso manquent au CSV. En juil. 2026, c'est le CSV
qui a raison (l'ODS avait raté la fin du 31/07). → deux vérités : temps
travaillé (CSV) et temps retenu pour la facturation (CSV + ajustements).

## Critères de fin (3 max, observables)
- [x] `ajustements:` dans `facturation.yml` (mois, commande, jours, motif) :
      9 lignes, calculées une fois depuis l'ODS, calipso et speasy seulement.
- [x] `/suivi?m=…` affiche chaque ajustement en fin de feuille (ligne sans
      date, en italique) et le compte dans les totaux ; `/suivi/synthese` aussi.
- [x] Exécuté total par commande = somme des feuilles mois de l'ODS : speasy
      34,23625 ; calipso_b 19,34875 ; calipso_a 12,9125 ; calipso_c +0,0625
      (31/07, voulu).

## Hors scope
- Saisie d'un ajustement depuis l'appli (formulaires, plus tard).
- colibri : non facturé, le CSV fait foi.

## Budget
- Temps décidé : 45 min
