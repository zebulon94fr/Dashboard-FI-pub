from flask import Blueprint, jsonify, request

from backend.dividendes import (
    add_dividende,
    delete_dividende,
    get_dividendes,
    update_dividende,
)
from routes.helpers import json_errors

bp = Blueprint("dividendes", __name__, url_prefix="/api")


@bp.route("/dividendes", methods=["GET"])
def list_dividendes():
    filtres = {
        "account_id": request.args.get("account_id") or None,
        "nom": request.args.get("nom") or None,
        "annee": request.args.get("annee") or None,
    }
    return jsonify(get_dividendes({k: v for k, v in filtres.items() if v}))


@bp.route("/dividendes", methods=["POST"])
@json_errors
def create_dividende():
    dividende_id = add_dividende(request.get_json(force=True))
    return jsonify({"ok": True, "id": dividende_id}), 201


@bp.route("/dividendes/<int:dividende_id>", methods=["PUT"])
@json_errors
def edit_dividende(dividende_id):
    update_dividende(dividende_id, request.get_json(force=True))
    return jsonify({"ok": True})


@bp.route("/dividendes/<int:dividende_id>", methods=["DELETE"])
@json_errors
def remove_dividende(dividende_id):
    delete_dividende(dividende_id)
    return jsonify({"ok": True})
