from flask import Blueprint, jsonify, request

from backend.claude import ClaudeError, call_claude

bp = Blueprint("claude", __name__, url_prefix="/api")


@bp.route("/claude", methods=["POST"])
def claude_proxy():
    """
    Relais vers l'API Anthropic. La clé ne transite pas par le dépôt : elle
    vient du formulaire, ou de settings.json.

    Une erreur de l'API est renvoyée en 400 avec son message d'origine — c'est
    une réponse de l'API, pas une panne du dashboard, et la distinction compte
    pour qui lit le message.
    """
    try:
        return jsonify(call_claude(request.get_json(force=True)))
    except ClaudeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
