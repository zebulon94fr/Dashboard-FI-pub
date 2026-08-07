#!/usr/bin/env bash
# Installe Dashboard FI comme service systemd : démarrage automatique au boot,
# redémarrage après un crash, et timers pour les cours, les sauvegardes et Telegram.
#
#   sudo ./scripts/install_service.sh                 # service + timers cours et sauvegarde
#   sudo ./scripts/install_service.sh --no-timers     # service seul
#   sudo ./scripts/install_service.sh --with-telegram # + résumé Telegram hebdomadaire
#
# Le script est idempotent : relancez-le après un « git pull » pour reprendre
# d'éventuelles modifications des unités.
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
UTILISATEUR="${DASHBOARD_USER:-dashboard}"
FICHIER_ENV=/etc/default/dashboard-fi
UNITES=/etc/systemd/system

AVEC_TIMERS=1
AVEC_TELEGRAM=0
for argument in "$@"; do
  case "$argument" in
    --no-timers)    AVEC_TIMERS=0 ;;
    --with-telegram) AVEC_TELEGRAM=1 ;;
    -h|--help)      sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $argument" >&2; exit 1 ;;
  esac
done

titre() { printf '\n\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }
alerte(){ printf '  \033[33m⚠ %s\033[0m\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "À lancer avec sudo : sudo $0" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd est requis (systemctl introuvable)." >&2; exit 1; }

# ── 1. Utilisateur dédié ────────────────────────────────────────────────────
titre "Utilisateur système"
if id -u "$UTILISATEUR" >/dev/null 2>&1; then
  info "« $UTILISATEUR » existe déjà."
else
  useradd --system --home-dir "$RACINE" --shell /usr/sbin/nologin "$UTILISATEUR"
  info "« $UTILISATEUR » créé."
fi

# ── 2. Environnement Python ─────────────────────────────────────────────────
titre "Environnement Python"
if [[ -x "$RACINE/.venv/bin/gunicorn" ]]; then
  info "Environnement virtuel déjà en place."
else
  command -v python3 >/dev/null || { echo "python3 est requis." >&2; exit 1; }
  python3 -m venv "$RACINE/.venv"
  "$RACINE/.venv/bin/pip" install --quiet --upgrade pip
  "$RACINE/.venv/bin/pip" install --quiet -r "$RACINE/requirements.txt"
  info "Dépendances installées dans .venv."
fi

# ── 3. Permissions ──────────────────────────────────────────────────────────
titre "Permissions"
chown -R "$UTILISATEUR":"$UTILISATEUR" "$RACINE"
chmod +x "$RACINE"/scripts/*.sh "$RACINE"/scripts/*.py
install -d -o "$UTILISATEUR" -g "$UTILISATEUR" "$RACINE/backups" "$RACINE/.cache"
info "Propriétaire : $UTILISATEUR — répertoire : $RACINE"

# ── 4. Configuration ────────────────────────────────────────────────────────
titre "Configuration"
if [[ -f "$FICHIER_ENV" ]]; then
  info "$FICHIER_ENV existe déjà, il n'est pas écrasé."
else
  sed "s#/opt/dashboard-fi#$RACINE#g" "$RACINE/deploy/dashboard-fi.env.example" > "$FICHIER_ENV"
  chmod 644 "$FICHIER_ENV"
  info "$FICHIER_ENV créé (HTTP par défaut, voir le fichier pour activer HTTPS)."
fi

# ── 5. Unités systemd ───────────────────────────────────────────────────────
# Les chemins et l'utilisateur sont réécrits à la volée : aucune édition
# manuelle nécessaire si l'installation n'est pas dans /opt/dashboard-fi.
titre "Unités systemd"
for source in "$RACINE"/deploy/dashboard-fi*.service "$RACINE"/deploy/dashboard-fi*.timer; do
  cible="$UNITES/$(basename "$source")"
  sed -e "s#/opt/dashboard-fi#$RACINE#g" \
      -e "s#^User=dashboard\$#User=$UTILISATEUR#" \
      -e "s#^Group=dashboard\$#Group=$UTILISATEUR#" \
      "$source" > "$cible"
  info "$(basename "$cible")"
done
systemctl daemon-reload

# ── 6. Activation ───────────────────────────────────────────────────────────
titre "Activation"
systemctl enable --now dashboard-fi.service
info "dashboard-fi.service : activé au démarrage et lancé."

if [[ $AVEC_TIMERS -eq 1 ]]; then
  systemctl enable --now dashboard-fi-refresh.timer dashboard-fi-backup.timer
  info "Timers cours (horaire) et sauvegarde (quotidienne) activés."
fi
if [[ $AVEC_TELEGRAM -eq 1 ]]; then
  systemctl enable --now dashboard-fi-telegram.timer
  info "Timer Telegram activé (samedi 9 h) — pensez à lancer scripts/set_telegram.py."
fi

# ── 7. Vérification ─────────────────────────────────────────────────────────
titre "État"
sleep 2
if systemctl is-active --quiet dashboard-fi.service; then
  port="$(grep -E '^DASHBOARD_PORT=' "$FICHIER_ENV" | cut -d= -f2)"
  schema="$(grep -E '^DASHBOARD_SCHEME=' "$FICHIER_ENV" | cut -d= -f2)"
  info "Service actif — ${schema:-http}://$(hostname -I | awk '{print $1}'):${port:-8742}"
else
  alerte "Le service n'est pas actif. Diagnostic :"
  info "  journalctl -u dashboard-fi -n 40 --no-pager"
  exit 1
fi

systemctl list-timers 'dashboard-fi*' --no-pager 2>/dev/null | head -6 || true

cat <<EOF

Commandes utiles :
  systemctl status dashboard-fi          état du service
  journalctl -u dashboard-fi -f          logs en direct
  systemctl restart dashboard-fi         après modification de $FICHIER_ENV
  systemctl list-timers 'dashboard-fi*'  prochaines exécutions planifiées
EOF
