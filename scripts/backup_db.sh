#!/usr/bin/env bash
# Sauvegarde dashboard.db (snapshot cohérent via `sqlite3 .backup`, sûr même en mode WAL)
# et purge les sauvegardes de plus de RETENTION_DAYS jours.
#
# Appelé par deploy/dashboard-fi-backup.timer, ou utilisable manuellement pour tester.
set -euo pipefail

cd "$(dirname "$0")/.."
RETENTION_DAYS="${DASHBOARD_BACKUP_RETENTION_DAYS:-14}"

mkdir -p backups
DEST="backups/dashboard-$(date +%F).db"

sqlite3 dashboard.db ".backup '${DEST}'"
echo "Sauvegarde créée : ${DEST}"

find backups -name 'dashboard-*.db' -mtime "+${RETENTION_DAYS}" -delete
echo "Sauvegardes de plus de ${RETENTION_DAYS} jours purgées."
