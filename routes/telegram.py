from flask import Blueprint, jsonify

from backend.telegram import send_weekly_summary

bp = Blueprint("telegram", __name__, url_prefix="/api")


@bp.route("/telegram/send", methods=["POST"])
def telegram_send():
    try:
        send_weekly_summary()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
