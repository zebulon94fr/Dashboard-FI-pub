#!/usr/bin/env python3
"""Dashboard FI — tableau de bord d'investissement (Flask + SQLite)."""
import logging
import sys

from flask import Flask, Response, request
from werkzeug.security import check_password_hash

import config
from backend.db import init_db
from backend.settings import load_settings
from routes import register_blueprints

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("dashboard")


def create_app():
    init_db()

    app = Flask(__name__, static_folder=config.STATIC_DIR, static_url_path="")
    register_blueprints(app)

    @app.before_request
    def require_auth():
        if request.method == "OPTIONS":
            return None
        if request.remote_addr in ("127.0.0.1", "::1"):
            return None  # appels locaux (ex. timer de rafraîchissement) toujours autorisés

        s = load_settings()
        username = s.get("authUsername")
        password_hash = s.get("authPasswordHash")
        if not username or not password_hash:
            return None  # authentification non configurée : accès libre (usage local)

        auth = request.authorization
        if not auth or auth.username != username or not check_password_hash(password_hash, auth.password):
            return Response(
                "Authentification requise", 401,
                {"WWW-Authenticate": 'Basic realm="Dashboard FI"'}
            )
        return None

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,x-api-key,anthropic-version"
        return response

    @app.route("/api/<path:_unused>", methods=["OPTIONS"])
    def options_handler(_unused):
        return ("", 200)

    return app


if __name__ == "__main__":
    ssl_context = (config.SSL_CERT, config.SSL_KEY) if config.SSL_CERT and config.SSL_KEY else None
    scheme = "https" if ssl_context else "http"

    log.info("╔══════════════════════════════════════╗")
    log.info("║   Dashboard FI — Flask / SQLite      ║")
    log.info("╚══════════════════════════════════════╝")
    log.info(f"  Écoute sur {scheme}://{config.HOST}:{config.PORT}")
    log.info(f"  Base de données : {config.DB_FILE}")
    log.info("  Ctrl+C pour arrêter")

    app = create_app()
    app.run(host=config.HOST, port=config.PORT, threaded=True, ssl_context=ssl_context)
