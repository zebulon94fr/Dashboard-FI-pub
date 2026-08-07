#!/usr/bin/env bash
# Démarre le serveur via gunicorn, avec ou sans TLS selon la configuration.
#
# Appelé par deploy/dashboard-fi.service, mais utilisable directement :
#   ./scripts/run_server.sh
#   DASHBOARD_PORT=9000 ./scripts/run_server.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# systemd fournit déjà ces variables via EnvironmentFile ; ce chargement sert
# aux lancements manuels, et ne remplace jamais une variable déjà définie.
if [[ -r /etc/default/dashboard-fi ]]; then
  while IFS='=' read -r cle valeur; do
    [[ "$cle" =~ ^[A-Z_]+$ ]] || continue
    [[ -n "${!cle:-}" ]] || export "$cle=$valeur"
  done < /etc/default/dashboard-fi
fi

GUNICORN="${DASHBOARD_VENV:-.venv}/bin/gunicorn"
if [[ ! -x "$GUNICORN" ]]; then
  echo "gunicorn introuvable ($GUNICORN)." >&2
  echo "Créez l'environnement virtuel : python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

args=(
  --workers "${DASHBOARD_WORKERS:-2}"
  --bind "${DASHBOARD_HOST:-0.0.0.0}:${DASHBOARD_PORT:-8742}"
  --access-logfile -
  --error-logfile -
)

# TLS demandé : on échoue explicitement si le certificat est inutilisable,
# plutôt que de servir en clair sans que personne ne s'en aperçoive.
if [[ -n "${DASHBOARD_SSL_CERT:-}" || -n "${DASHBOARD_SSL_KEY:-}" ]]; then
  if [[ ! -r "${DASHBOARD_SSL_CERT:-}" || ! -r "${DASHBOARD_SSL_KEY:-}" ]]; then
    echo "TLS demandé mais le certificat ou la clé est illisible :" >&2
    echo "  DASHBOARD_SSL_CERT=${DASHBOARD_SSL_CERT:-<vide>}" >&2
    echo "  DASHBOARD_SSL_KEY=${DASHBOARD_SSL_KEY:-<vide>}" >&2
    echo "Générez-les avec ./scripts/generate_cert.sh, ou commentez ces deux lignes" >&2
    echo "dans /etc/default/dashboard-fi pour servir en HTTP." >&2
    exit 1
  fi
  args+=(--certfile "$DASHBOARD_SSL_CERT" --keyfile "$DASHBOARD_SSL_KEY")
fi

exec "$GUNICORN" "${args[@]}" 'app:create_app()'
