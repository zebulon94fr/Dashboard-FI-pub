import base64
import binascii

from flask import Blueprint, jsonify, request

from backend.import_csv import analyser, executer
from backend.transactions import TransactionError
from routes.helpers import json_errors

bp = Blueprint("import_csv", __name__, url_prefix="/api")


def _contenu(payload):
    """
    Contenu du fichier : des octets si le client les a encodés, du texte sinon.

    Un classeur est binaire et ne survivrait pas à un aller-retour en JSON ;
    l'interface envoie donc toujours les octets bruts, ce qui règle du même
    coup la question de l'encodage d'un CSV — c'est le serveur qui le devine,
    sur les octets d'origine plutôt que sur un texte déjà mal décodé.
    """
    encode = payload.get("contenu_b64")
    if encode:
        try:
            return base64.b64decode(encode, validate=True)
        except (binascii.Error, ValueError):
            raise TransactionError("Fichier illisible : le contenu transmis est corrompu.")
    return payload.get("contenu") or ""


@bp.route("/import/analyse", methods=["POST"])
@json_errors
def analyse():
    """En-têtes, aperçu et correspondance proposée — rien n'est écrit."""
    payload = request.get_json(silent=True) or {}
    return jsonify(analyser(_contenu(payload)))


@bp.route("/import/executer", methods=["POST"])
@json_errors
def importer():
    """Aperçu détaillé, ou import effectif si `valider` est vrai."""
    payload = request.get_json(silent=True) or {}
    return jsonify(executer(
        _contenu(payload),
        payload.get("account_id"),
        payload.get("correspondance") or {},
        payload.get("options") or {},
        valider=bool(payload.get("valider")),
    ))
