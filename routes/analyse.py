from flask import Blueprint, jsonify, request

from backend.analyse import analyse_complete, repartition_classes
from backend.dividendes import rendements
from backend.rebalancing import get_rebalancing, save_cibles_classes
from catalog import public_classes
from routes.helpers import json_errors

bp = Blueprint("analyse", __name__, url_prefix="/api")


@bp.route("/classes", methods=["GET"])
def classes():
    """Catalogue des classes d'actifs et répartition courante."""
    return jsonify({"catalogue": public_classes(), "repartition": repartition_classes()})


@bp.route("/analyse", methods=["GET"])
@json_errors
def analyse():
    """Risque, concentration, devises, attribution et contributions."""
    return jsonify(analyse_complete(int(request.args.get("days", "365"))))


@bp.route("/rendements", methods=["GET"])
@json_errors
def rendements_dividendes():
    """Rendement courant, sur prix de revient, et taux de prélèvement effectif."""
    return jsonify(rendements())


@bp.route("/rebalancing", methods=["GET"])
@json_errors
def rebalancing():
    """Écarts par classe d'actifs et mouvements recommandés."""
    return jsonify(get_rebalancing(
        apport=float(request.args.get("apport", "0") or 0),
        bande_relative=float(request.args.get("bande", "0.25") or 0.25),
        ordre_minimum=float(request.args.get("ordre_min", "100") or 100),
    ))


@bp.route("/rebalancing/cibles", methods=["POST"])
@json_errors
def sauver_cibles():
    """Enregistre l'allocation cible par classe d'actifs."""
    payload = request.get_json(silent=True) or {}
    save_cibles_classes(payload.get("cibles") or {})
    return jsonify({"ok": True})
