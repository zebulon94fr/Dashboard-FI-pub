from flask import Blueprint, jsonify

from backend.positions import load_portfolio

bp = Blueprint("data", __name__, url_prefix="/api")


@bp.route("/data", methods=["GET"])
def get_data():
    """Portefeuille complet : comptes, positions et historique."""
    return jsonify(load_portfolio())
