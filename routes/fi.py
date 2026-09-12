from flask import Blueprint, jsonify, request

from backend.fi import get_reglages, metriques, save_reglages
from routes.helpers import json_errors

bp = Blueprint("fi", __name__, url_prefix="/api")


@bp.route("/fi", methods=["GET"])
@json_errors
def fi():
    """Patrimoine net, frais réels et métriques d'indépendance financière."""
    return jsonify(metriques())


@bp.route("/fi/reglages", methods=["GET"])
@json_errors
def lire_reglages():
    return jsonify(get_reglages())


@bp.route("/fi/reglages", methods=["POST"])
@json_errors
def ecrire_reglages():
    """Dépenses, épargne et horizon : la seule saisie que le dashboard ne déduit pas."""
    return jsonify(save_reglages(request.get_json(silent=True) or {}))
