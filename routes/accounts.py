from flask import Blueprint, jsonify, request

from backend.accounts import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    save_cibles,
    update_account,
)
from catalog import public_types, DEVISES
from routes.helpers import json_errors

bp = Blueprint("accounts", __name__, url_prefix="/api")


@bp.route("/account-types", methods=["GET"])
def account_types():
    """Catalogue des types d'enveloppes proposés à la création d'un compte."""
    return jsonify({"types": public_types(), "devises": DEVISES})


@bp.route("/accounts", methods=["GET"])
def get_accounts():
    return jsonify(list_accounts())


@bp.route("/accounts", methods=["POST"])
@json_errors
def post_account():
    account_id = create_account(request.get_json(force=True))
    return jsonify({"ok": True, "id": account_id, "account": get_account(account_id)}), 201


@bp.route("/accounts/cibles", methods=["POST"])
@json_errors
def post_cibles():
    save_cibles(request.get_json(force=True).get("cibles", {}))
    return jsonify({"ok": True})


@bp.route("/accounts/<int:account_id>", methods=["PUT"])
@json_errors
def put_account(account_id):
    update_account(account_id, request.get_json(force=True))
    return jsonify({"ok": True, "account": get_account(account_id)})


@bp.route("/accounts/<int:account_id>", methods=["DELETE"])
@json_errors
def remove_account(account_id):
    delete_account(account_id)
    return jsonify({"ok": True})
