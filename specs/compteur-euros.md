# SPEC — compteur euros
Date : 2026-07-16
Statut : terminé

## Objectif (une phrase)
Voir sur la page web `/projects`, pour chaque projet facturable, le montant
en euros accumulé depuis la date de sa dernière facture (TJM et date de
dernière facture configurés par projet).

## Critères de fin (3 max, observables)
- [x] `projects-config.yml` accepte `tjm` et `derniere_facture` par projet
- [x] `/projects` affiche, par projet facturable, le montant € accumulé depuis
      la date de dernière facture
- [x] un projet sans TJM n'affiche pas de montant et ne casse pas la page
      (vérifié sur bht et perso, sans code spécifique)

### Suite décidée le 16/07 (budget 1 h) — la feature n'était pas finie
- [x] le total du bas de `/projects` s'affiche aussi sur `/live`, rafraîchi en
      direct par la boucle `poll()` existante (3 s), et suit le cookie 1/4h

## Hors scope — explicitement PAS dans cette feature
- La page `/factures` (nb_jours_budgétés / réalisés / facturés) — évolution
  possible, notée dans IDEAS.md, pas ici.
- Le calcul du montant depuis les vraies factures : ici c'est TJM × jours
  travaillés, aucune lecture de facture.
- Toute écriture / édition de la date de dernière facture depuis le web : la
  config se modifie à la main dans le YAML.
- Le CLI : web uniquement.

## Budget
- Temps décidé : 1 h  (décidé AVANT le plan)
- Seuil d'arrêt : budget × 1.5 = 1 h 30
  → si atteint : STOP, commit, re-décision à froid demain.

## Plan (rempli en mode plan)
| Tâche | Estimation |
|---|---|
| Config `tjm` / `derniere_facture` dans projects-config.yml | 5 min |
| Calcul (`_project_billing_config`, `project_minutes_since`, `project_amounts`) | 20 min |
| Page `/projects` + entrée de menu | 20 min |
| Tests | 10 min |
| **Total** | **55 min** |

→ Si Total > Budget : couper du scope ICI, avant de coder.

## Journal de session
<!-- une ligne par session : date, durée, où j'en suis, prochaine étape -->
- 2026-07-16 (1 h) — page `/projects` dans `webhook_receiver.py` (pas l'ancienne
  app), calcul depuis le CSV webhook, arrondi 1/4h branché sur le cookie `round`
  existant. speasy et calipso tarifés, bht sans TJM donc absent du tableau.
  Clôturée trop tôt : voir ci-dessous.
- 2026-07-16 (1 h) — total à facturer ajouté sur `/live`, servi par
  `/api/rows` et rafraîchi par le `poll()` existant. `billable_total()` est la
  source unique des trois affichages (`/live`, bas de `/projects`, API), et un
  test vérifie qu'ils ne peuvent pas diverger. Feature terminée.
  Suite possible : la grosse feature « activité par projet » sur `/projects`
  (IDEAS.md).
