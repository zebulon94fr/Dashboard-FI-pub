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
