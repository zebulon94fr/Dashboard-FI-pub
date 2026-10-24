#!/usr/bin/env bash
# Inscrit au journal les échéances dues des versements programmés.
# Appelé par deploy/dashboard-fi-versements.timer, ou manuellement pour tester.
#
# L'opération est idempotente et rattrapante : la relancer ne double rien, et
# une exécution manquée est rattrapée au passage suivant.
set -euo pipefail

PORT="${DASHBOARD_PORT:-8742}"
SCHEME="${DASHBOARD_SCHEME:-https}"

curl -sk -X POST -H 'Content-Type: application/json' -d '{}' \
  "${SCHEME}://127.0.0.1:${PORT}/api/programmes/executer"
echo ""
