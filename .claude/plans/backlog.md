# Backlog — futures tâches time_tracking

## 1. Bug : export `table` ne remonte pas le projet `carangues`
- Vérifier pourquoi `carangues` est absent de `timer report --view table`
- Probablement absent de `EXPORT_PROJECTS` dans `config.yml`, ou nom différent dans `pomofocus.csv`

## 2. Harmoniser / séparer les features CLI vs web
- Auditer ce qui existe côté CLI (`core/`) et côté web (`web/tools/`)
- Clarifier quelles features appartiennent à quel périmètre
- Objectif : pas de duplication de responsabilité, frontières claires

## 3. Factoriser les fonctions communes CLI / web
- Les deux pipelines partagent la config mais ont des parsers séparés (ex. pomofocus lu dans `core/data.py` ET dans `web/tools/histories.py`)
- Identifier les fonctions dupliquées et extraire dans un module commun (ex. `core/` ou nouveau `shared/`)

## 4. Visualisation : uniquement web
- À terme, toute visualisation (pomofocus analysis + projects analysis) doit passer par le web
- Le CLI reste pour les exports texte/CSV, pas pour les plots matplotlib
- Implique de migrer `core/plots.py` (day-bars, annual plot) vers `web/`

## 5. Simplifier / automatiser le pipeline initial
Pipeline actuel :
1. pomofocus.io → saisie
2. Export → `report.csv`
3. `timer pomo-merge` → `pomofocus.csv`
4. `timer report --view export` → CSV
5. Édition manuelle `suivi_chantiers.ods` (renommage calipso → calipso_a/b)
6. `timer eighty-hours`

Pistes à explorer :
- Réduire les étapes manuelles (détection auto du report.csv, renommage calipso assisté)
- Automatiser l'alimentation de `suivi_chantiers.ods` ou le remplacer par une source programmatique
