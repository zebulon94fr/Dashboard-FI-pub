from flask import Blueprint, jsonify, request

from backend.settings import load_settings, save_settings

bp = Blueprint("settings", __name__, url_prefix="/api")


@bp.route("/settings", methods=["GET"])
def get_settings():
    s = load_settings()
    return jsonify({"hasKey": bool(s.get("anthropicKey", ""))})


@bp.route("/settings", methods=["POST"])
def post_settings():
    try:
        payload = request.get_json(force=True)
        s = load_settings()
        if "anthropicKey" in payload:
            s["anthropicKey"] = payload["anthropicKey"]
        save_settings(s)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/settings/key", methods=["GET"])
def get_settings_key():
    s = load_settings()
    return jsonify({"key": s.get("anthropicKey", "")})
