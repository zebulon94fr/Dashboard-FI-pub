#!/usr/bin/env bash
# Envoie sur Telegram le rapport du mois écoulé.
# Appelé par deploy/dashboard-fi-rapport.timer le 1er de chaque mois, ou
# manuellement pour tester.
#
# Sans argument, c'est le mois précédent qui est rapporté — un rapport du mois
# en cours n'aurait qu'une journée à raconter. Un mois peut être passé en
# argument au format AAAA-MM pour renvoyer un rapport ancien.
set -euo pipefail

PORT="${DASHBOARD_PORT:-8742}"
SCHEME="${DASHBOARD_SCHEME:-https}"
MOIS="${1:-}"

if [ -n "$MOIS" ]; then
  CORPS="{\"mois\":\"${MOIS}\"}"
else
  CORPS='{}'
fi

curl -sk -X POST -H 'Content-Type: application/json' -d "$CORPS" \
  "${SCHEME}://127.0.0.1:${PORT}/api/telegram/rapport"
echo ""
