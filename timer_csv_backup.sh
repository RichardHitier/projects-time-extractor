#!/bin/bash
# Sauvegarde du CSV de prod du webhook Pomofocus.
#
# Le fichier vit en un seul exemplaire sur le VPS (volume docker webhook-data/)
# et porte tout l'historique depuis sept. 2022. On le tire ici via l'endpoint
# public /api/csv, dans un dossier que rclone_to_bckp.sh (cron horaire) pousse
# déjà vers gdrive:backup/00PRO — donc rien à installer sur le VPS.
#
# Un exemplaire par jour, réécrit à chaque passage : la sauvegarde du jour suit
# la journée de travail, et l'historique quotidien est conservé.
#
# cron :  50 * * * * /home/richard/bin/timer_csv_backup.sh
#         (à :50, pour que rclone trouve un fichier frais à :00)

set -uo pipefail

URL="http://timer.co-libri.org/api/csv"
DEST_DIR="$HOME/00PRO/backups/timer"
LOG_FILE="$HOME/timer-csv-backup.log"
HEADER="date,project,task,minutes,startTime,endTime"

log() { echo "$(date '+%F %T') $*" >> "$LOG_FILE"; }

mkdir -p "$DEST_DIR"
tmp=$(mktemp) || exit 1
trap 'rm -f "$tmp"' EXIT

if ! curl -fsS --max-time 30 "$URL" -o "$tmp"; then
    log "ERREUR : téléchargement impossible ($URL)"
    exit 1
fi

# Garde-fou 1 : c'est bien notre CSV, pas une page d'erreur ni une redirection.
if [ "$(head -1 "$tmp")" != "$HEADER" ]; then
    log "ERREUR : en-tête inattendu — rien écrit"
    exit 1
fi

# Garde-fou 2 : jamais plus court que la dernière sauvegarde. Le CSV ne fait que
# grandir ; s'il rétrécit, c'est un incident (fichier tronqué, volume vide après
# un redéploiement…) et l'écraser détruirait justement ce qu'on veut protéger.
lignes=$(wc -l < "$tmp")
dernier=$(ls -1 "$DEST_DIR"/pomofocus_webhook-*.csv 2>/dev/null | tail -1)
if [ -n "$dernier" ]; then
    ref=$(wc -l < "$dernier")
    if [ "$lignes" -lt "$ref" ]; then
        log "ALERTE : $lignes lignes contre $ref dans $(basename "$dernier") — rien écrit"
        exit 1
    fi
fi

cible="$DEST_DIR/pomofocus_webhook-$(date +%Y%m%d).csv"
mv "$tmp" "$cible"
log "OK : $lignes lignes -> $(basename "$cible")"
