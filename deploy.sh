#!/usr/bin/env bash
# Déploiement du récepteur webhook sur le VPS.
# Lancé par GitHub Actions en SSH après un push sur main (.github/workflows/deploy.yml),
# ou manuellement sur l'hôte VPS : ./deploy.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "→ Récupération de main"
git fetch --prune origin
git reset --hard origin/main      # le repo VPS est un miroir de main

echo "→ Build de l'image webhook"
docker compose build webhook      # nginx = image stock, pas de build

echo "→ Redémarrage (recrée les conteneurs dont l'image a changé)"
docker compose up -d

echo "→ Nettoyage des images orphelines"
docker image prune -f

echo "✓ Déploiement terminé"
