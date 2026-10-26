from flask import Blueprint, jsonify, request

from backend.telegram import send_monthly_report, send_weekly_summary

bp = Blueprint("telegram", __name__, url_prefix="/api")


@bp.route("/telegram/send", methods=["POST"])
def telegram_send():
    try:
        send_weekly_summary()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/telegram/rapport", methods=["POST"])
def telegram_rapport():
    """Envoie le rapport du mois écoulé — appelé par la minuterie du 1er."""
    try:
        mois = send_monthly_report((request.get_json(silent=True) or {}).get("mois"))
        return jsonify({"ok": True, "mois": mois})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
