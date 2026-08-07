"""Petits utilitaires partagés par les blueprints."""
import functools
import logging

from flask import jsonify

log = logging.getLogger("dashboard")


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
            return jsonify({"error": str(e)}), 500
    return wrapper
