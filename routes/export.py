import datetime

from flask import Blueprint, Response

from backend.export import generate_csv
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
