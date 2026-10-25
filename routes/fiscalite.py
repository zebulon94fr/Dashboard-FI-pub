from flask import Blueprint, jsonify, request

from backend.fiscalite import abattements_consommes, cessions, plan_retrait
from routes.helpers import json_errors

bp = Blueprint("fiscalite", __name__, url_prefix="/api")


def _booleen(nom):
    return (request.args.get(nom) or "").strip().lower() in ("1", "true", "oui")


@bp.route("/fiscalite/retrait", methods=["GET"])
@json_errors
def retrait():
    """D'où sortir une somme au moindre coût fiscal."""
    try:
        besoin = float(request.args.get("besoin") or 0)
    except ValueError:
        besoin = 0.0
    return jsonify(plan_retrait(besoin, couple=_booleen("couple"),
                                inclure_bloquees=_booleen("inclure_bloquees")))


@bp.route("/fiscalite/abattements", methods=["GET"])
@json_errors
def abattements():
    """Ce qu'il reste à retirer en franchise sur l'année civile."""
    return jsonify(abattements_consommes(request.args.get("annee"),
                                         couple=_booleen("couple")))


@bp.route("/fiscalite/cessions", methods=["GET"])
@json_errors
def cessions_annee():
    """Cessions de l'année, détaillées par formulaire."""
    return jsonify(cessions(request.args.get("annee")))
