from flask import Blueprint, jsonify, request

from backend.benchmark import get_benchmark
from backend.performance import compute_tri, compute_tri_portefeuille, compute_twr
from routes.helpers import json_errors

bp = Blueprint("benchmark", __name__, url_prefix="/api")


@bp.route("/benchmark", methods=["GET"])
@json_errors
def benchmark():
    return jsonify(get_benchmark(int(request.args.get("days", "365"))))


@bp.route("/tri", methods=["GET"])
@json_errors
def tri():
    nom = request.args.get("nom", "")
    account_id = int(request.args.get("account_id", "0"))
    return jsonify({**compute_tri(nom, account_id), "nom": nom, "account_id": account_id})


@bp.route("/performance", methods=["GET"])
@json_errors
def performance():
    """TWR en base 100 et TRI du portefeuille sur la période demandée."""
    jours = int(request.args.get("days", "365"))
    account_id = request.args.get("account_id")
    return jsonify({
        "twr": compute_twr(jours, int(account_id) if account_id else 0),
        "tri": compute_tri_portefeuille(account_id),
    })
