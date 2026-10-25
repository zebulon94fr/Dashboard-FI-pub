import datetime

from flask import Blueprint, Response, request

from backend.export import generate_csv, generate_csv_cessions
from backend.fiscalite import cessions
from backend.positions import load_portfolio

bp = Blueprint("export", __name__, url_prefix="/api")


@bp.route("/export/csv", methods=["GET"])
def export_csv():
    corps = generate_csv(load_portfolio()).encode("utf-8-sig")
    return Response(
        corps,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="portefeuille_{datetime.date.today()}.csv"'
        },
    )


@bp.route("/export/cessions", methods=["GET"])
def export_cessions():
    """Cessions de l'année au format des formulaires 2074 et 2086."""
    detail = cessions(request.args.get("annee"))
    corps = generate_csv_cessions(detail).encode("utf-8-sig")
    return Response(
        corps,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="cessions_{detail["annee"]}.csv"'
        },
    )
