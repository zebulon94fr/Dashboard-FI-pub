#!/usr/bin/env bash
# Génère un certificat TLS auto-signé pour le dashboard (usage local/LAN).
#
# Usage :
#   ./scripts/generate_cert.sh [IP-ou-hostname supplémentaire ...]
#
# Exemple (accès depuis le réseau local) :
#   ./scripts/generate_cert.sh 192.168.1.50 dashboard.local
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p certs

SAN="DNS:localhost,IP:127.0.0.1"
for name in "$@"; do
  if [[ "$name" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    SAN="$SAN,IP:$name"
  else
    SAN="$SAN,DNS:$name"
  fi
done

echo "Génération du certificat auto-signé (SAN: $SAN)…"
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout certs/key.pem -out certs/cert.pem \
  -days 825 \
  -subj "/CN=dashboard-fi" \
  -addext "subjectAltName=$SAN"

chmod 600 certs/key.pem

echo ""
echo "OK : certs/cert.pem + certs/key.pem (valide 825 jours)"
echo "Le navigateur affichera un avertissement \"certificat non fiable\" la première fois — c'est normal pour un certificat auto-signé, il suffit de l'accepter."
echo ""
echo "Test local :"
echo "  DASHBOARD_SSL_CERT=certs/cert.pem DASHBOARD_SSL_KEY=certs/key.pem python app.py"
