from flask import Blueprint, jsonify, request

from backend.transactions import (
    add_transaction,
    delete_transaction,
    get_transactions,
    plus_values_realisees,
    update_transaction,
)
from catalog import public_transaction_types
from routes.helpers import json_errors

bp = Blueprint("transactions", __name__, url_prefix="/api")


@bp.route("/transaction-types", methods=["GET"])
def transaction_types():
    """Types de mouvement acceptés par le journal."""
    return jsonify({"types": public_transaction_types()})


@bp.route("/transactions", methods=["GET"])
@json_errors
def liste():
    filtres = {cle: request.args.get(cle) for cle in
               ("account_id", "position_id", "type", "annee")}
    return jsonify(get_transactions({k: v for k, v in filtres.items() if v}))


@bp.route("/transactions", methods=["POST"])
@json_errors
def creer():
    return jsonify({"id": add_transaction(request.get_json(silent=True) or {})}), 201


@bp.route("/transactions/<int:transaction_id>", methods=["PUT"])
@json_errors
def modifier(transaction_id):
    update_transaction(transaction_id, request.get_json(silent=True) or {})
    return jsonify({"ok": True})


@bp.route("/transactions/<int:transaction_id>", methods=["DELETE"])
@json_errors
def supprimer(transaction_id):
    delete_transaction(transaction_id)
    return jsonify({"ok": True})


@bp.route("/plus-values", methods=["GET"])
@json_errors
def plus_values():
    """Plus-values réalisées, reconstituées depuis le journal."""
    return jsonify({
        "lignes": plus_values_realisees(
            request.args.get("account_id"), request.args.get("annee")
        ),
    })
