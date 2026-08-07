from flask import Blueprint, jsonify, request

from backend.positions import (
    create_position,
    delete_position,
    load_positions,
    move_position,
    update_position,
)
from routes.helpers import json_errors

bp = Blueprint("positions", __name__, url_prefix="/api")


@bp.route("/accounts/<int:account_id>/positions", methods=["GET"])
def get_positions(account_id):
    return jsonify(load_positions(account_id))


@bp.route("/accounts/<int:account_id>/positions", methods=["POST"])
@json_errors
def post_position(account_id):
    position_id = create_position(account_id, request.get_json(force=True))
    return jsonify({"ok": True, "id": position_id}), 201


@bp.route("/positions/<int:position_id>", methods=["PUT"])
@json_errors
def put_position(position_id):
    payload = request.get_json(force=True)
    if payload.get("account_id"):
        move_position(position_id, int(payload["account_id"]))
    update_position(position_id, payload)
    return jsonify({"ok": True})


@bp.route("/positions/<int:position_id>", methods=["DELETE"])
@json_errors
def remove_position(position_id):
    delete_position(position_id)
    return jsonify({"ok": True})
