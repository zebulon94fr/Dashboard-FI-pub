from flask import Blueprint, jsonify, request

from backend.programmes import (
    FREQUENCES,
    TYPES_PROGRAMMABLES,
    add_programme,
    delete_programme,
    executer,
    list_programmes,
    update_programme,
)
from routes.helpers import json_errors

bp = Blueprint("programmes", __name__, url_prefix="/api")


@bp.route("/programmes", methods=["GET"])
@json_errors
def liste():
    return jsonify({
        "programmes": list_programmes(),
        "frequences": [{"id": f, **info} for f, info in FREQUENCES.items()],
        "types": TYPES_PROGRAMMABLES,
    })


@bp.route("/programmes", methods=["POST"])
@json_errors
def creer():
    return jsonify({"id": add_programme(request.get_json(silent=True) or {})}), 201


@bp.route("/programmes/<int:programme_id>", methods=["PUT"])
@json_errors
def modifier(programme_id):
    update_programme(programme_id, request.get_json(silent=True) or {})
    return jsonify({"ok": True})


@bp.route("/programmes/<int:programme_id>", methods=["DELETE"])
@json_errors
def supprimer(programme_id):
    delete_programme(programme_id)
    return jsonify({"ok": True})


@bp.route("/programmes/executer", methods=["POST"])
@json_errors
def lancer():
    """Inscrit les échéances dues. Appelée par la minuterie et par l'interface."""
    jusqu_a = (request.get_json(silent=True) or {}).get("jusqu_a")
    return jsonify(executer(jusqu_a))
