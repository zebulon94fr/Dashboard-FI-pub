from flask import Blueprint, jsonify, request

from backend.db import get_db
from backend.stats import get_stats

bp = Blueprint("stats", __name__, url_prefix="/api")


@bp.route("/stats", methods=["GET"])
def stats():
    return jsonify(get_stats())


@bp.route("/positions/<int:position_id>/history", methods=["GET"])
def position_history(position_id):
    """Série intraday des cours d'une position (onglet détail d'un compte)."""
    jours = int(request.args.get("days", "7"))
    with get_db() as db:
        rows = db.execute("""
            SELECT ts, cours, variation FROM price_history
            WHERE position_id=? AND ts >= datetime('now', ? || ' days')
            ORDER BY ts ASC
        """, (position_id, f"-{jours}")).fetchall()
    return jsonify([dict(r) for r in rows])
