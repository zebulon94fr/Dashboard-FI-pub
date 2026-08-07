from flask import Blueprint, jsonify, request

from backend.benchmark import get_benchmark
from backend.dividendes import compute_tri
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
    return jsonify({"tri": compute_tri(nom, account_id), "nom": nom, "account_id": account_id})
