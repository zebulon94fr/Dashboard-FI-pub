from flask import Blueprint, jsonify, request

from backend.claude import call_claude

bp = Blueprint("claude", __name__, url_prefix="/api")


@bp.route("/claude", methods=["POST"])
def claude_proxy():
    try:
        payload = request.get_json(force=True)
        result = call_claude(payload)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
