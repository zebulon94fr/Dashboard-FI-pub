from flask import Blueprint, jsonify, request

from backend.import_csv import analyser, executer
from routes.helpers import json_errors

bp = Blueprint("import_csv", __name__, url_prefix="/api")


@bp.route("/import/analyse", methods=["POST"])
@json_errors
def analyse():
    """En-têtes, aperçu et correspondance proposée — rien n'est écrit."""
    payload = request.get_json(silent=True) or {}
    return jsonify(analyser(payload.get("contenu") or ""))


@bp.route("/import/executer", methods=["POST"])
@json_errors
def importer():
    """Aperçu détaillé, ou import effectif si `valider` est vrai."""
    payload = request.get_json(silent=True) or {}
    return jsonify(executer(
        payload.get("contenu") or "",
        payload.get("account_id"),
        payload.get("correspondance") or {},
        payload.get("options") or {},
        valider=bool(payload.get("valider")),
    ))
