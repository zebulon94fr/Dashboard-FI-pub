from flask import Blueprint, jsonify

from backend.db import get_db
from backend.quotes import fetch_quotes
from routes.helpers import json_errors

bp = Blueprint("quotes", __name__, url_prefix="/api")


@bp.route("/quotes", methods=["GET"])
@json_errors
def quotes():
    actualisees, usd_eur, splits = fetch_quotes()
    with get_db() as db:
        dernier = db.execute(
            "SELECT ts FROM history_intraday ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return jsonify({
        "ok": actualisees > 0,
        "positions": actualisees,
        "usd_eur": usd_eur,
        "splits": [{"nom": nom, "ratio": ratio} for nom, ratio in splits],
        "lastUpdate": dernier["ts"] if dernier else "",
    })
