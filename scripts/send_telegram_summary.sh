#!/usr/bin/env bash
# Déclenche l'envoi du résumé hebdomadaire Telegram en local.
# Appelé par deploy/dashboard-fi-telegram.timer, ou utilisable manuellement pour tester.
#
# DASHBOARD_SCHEME=http ./scripts/send_telegram_summary.sh   # si le serveur local tourne sans TLS
set -euo pipefail

PORT="${DASHBOARD_PORT:-8742}"
SCHEME="${DASHBOARD_SCHEME:-https}"

curl -sk -X POST "${SCHEME}://127.0.0.1:${PORT}/api/telegram/send"
echo ""
