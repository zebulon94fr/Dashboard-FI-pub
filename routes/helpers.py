"""Petits utilitaires partagés par les blueprints."""
import functools
import logging

from flask import jsonify

log = logging.getLogger("dashboard")


# « attempt to write a readonly database » ne dit rien à qui regarde un
# dashboard : ni que c'est un problème de droits, ni où le chercher. Le
# diagnostic complet est dans le journal du service (voir backend/db.py) ;
# l'interface en donne la version courte.
LECTURE_SEULE = (
    "La base de données n'est pas accessible en écriture : rien ne peut y être "
    "enregistré. C'est un problème de droits sur le fichier, ou d'isolation du "
    "service — le journal du serveur en donne le détail et la marche à suivre "
    "(« journalctl -u dashboard-fi »)."
)


def json_errors(fn):
    """Transforme les erreurs de validation en 400 et le reste en 500, au format JSON."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as e:                       # erreurs de validation métier
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            log.exception(f"{fn.__name__} : {e}")
            if "readonly database" in str(e).lower():
                return jsonify({"error": LECTURE_SEULE}), 500
            return jsonify({"error": str(e)}), 500
    return wrapper
