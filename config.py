"""Chemins et configuration globale."""
import os

PORT      = int(os.environ.get("DASHBOARD_PORT", 8742))
HOST      = os.environ.get("DASHBOARD_HOST", "0.0.0.0")

# HTTPS optionnel : renseigner les deux pour servir en TLS (voir scripts/generate_cert.sh)
SSL_CERT = os.environ.get("DASHBOARD_SSL_CERT")
SSL_KEY  = os.environ.get("DASHBOARD_SSL_KEY")

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR    = os.path.join(BASE_DIR, "static")
DB_FILE       = os.environ.get("DASHBOARD_DB") or os.path.join(BASE_DIR, "dashboard.db")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

# Devise de référence : toutes les valorisations sont converties dans celle-ci.
DEVISE_REF = "EUR"

# Délais des requêtes longues. Une analyse IA ou une actualisation de cours
# demande bien plus que les quelques secondes d'un appel ordinaire.
#
# L'ordre entre les deux est ce qui compte : le worker doit **survivre** à
# l'appel sortant, sinon il est tué pendant l'attente et le navigateur reçoit
# un 500 nu, sans le message qui dirait ce qui s'est passé. Le délai de l'appel
# est donc toujours le plus court des deux.
CLAUDE_TIMEOUT = int(os.environ.get("DASHBOARD_CLAUDE_TIMEOUT", 120))
WORKER_TIMEOUT = int(os.environ.get("DASHBOARD_TIMEOUT", 180))
