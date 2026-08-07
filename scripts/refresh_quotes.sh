#!/usr/bin/env bash
# Déclenche un rafraîchissement des cours (GET /api/quotes) en local.
# Appelé par deploy/dashboard-fi-refresh.timer, ou utilisable manuellement pour tester.
#
# DASHBOARD_SCHEME=http ./scripts/refresh_quotes.sh   # si le serveur local tourne sans TLS
set -euo pipefail

PORT="${DASHBOARD_PORT:-8742}"
SCHEME="${DASHBOARD_SCHEME:-https}"

curl -sk "${SCHEME}://127.0.0.1:${PORT}/api/quotes"
echo ""
