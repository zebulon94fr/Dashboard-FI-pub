import datetime

from flask import Blueprint, Response, jsonify, request

from backend.db import get_db
from backend.rapport import (RapportError, mois_precedent, rapport_mensuel,
                             rapport_periode)
from backend.rapport_html import page_rapport
from routes.helpers import json_errors

bp = Blueprint("rapport", __name__)


@bp.route("/rapport", methods=["GET"])
@bp.route("/rapport/<mois>", methods=["GET"])
def rapport(mois=None):
    """
    Rapport en page HTML autonome, sur un mois ou sur une fenêtre glissante.

    `/rapport/2026-09` pour un mois, `/rapport?jours=90` pour les trois derniers
    mois — ce que demande le bouton de l'onglet Historique, dont la période est
    déjà choisie à l'écran. Sans l'un ni l'autre, le mois qui vient de finir.

    Hors de `/api` à dessein : c'est une page qu'on garde, qu'on imprime et
    qu'on transfère, pas un appel du frontend.
    """
    jours = request.args.get("jours")
    try:
        donnees = (rapport_periode(jours) if jours and not mois
                   else rapport_mensuel(mois or request.args.get("mois")))
    except RapportError as e:
        return Response(
            f"<!doctype html><meta charset='utf-8'><p style='font-family:sans-serif'>{e}</p>",
            status=400, mimetype="text/html",
        )
    return Response(page_rapport(donnees), mimetype="text/html")


@bp.route("/api/rapport", methods=["GET"])
@json_errors
def rapport_json():
    """Les mêmes données, pour un script ou un autre client."""
    jours = request.args.get("jours")
    return jsonify(rapport_periode(jours) if jours
                   else rapport_mensuel(request.args.get("mois")))


@bp.route("/api/rapport/mois-disponibles", methods=["GET"])
@json_errors
def mois_disponibles():
    """Mois couverts par l'historique, du plus récent au plus ancien."""
    with get_db() as db:
        lignes = db.execute(
            "SELECT DISTINCT substr(date, 1, 7) mois FROM history_daily "
            "WHERE account_id = 0 ORDER BY mois DESC"
        ).fetchall()
    return jsonify({
        "mois": [ligne["mois"] for ligne in lignes],
        "defaut": mois_precedent(),
        "aujourdhui": datetime.date.today().isoformat(),
    })
