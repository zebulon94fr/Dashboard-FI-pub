#!/usr/bin/env python3
"""Amorce les clôtures quotidiennes par position depuis l'historique existant.

Les corrélations, la contribution au risque et le bêta se calculent sur une
série de prix par position (table `cours_quotidiens`), que le dashboard
commence à remplir à chaque actualisation des cours. Sans amorçage, il faut
donc attendre une vingtaine de séances avant que ces mesures apparaissent.

Ce script reconstitue les journées déjà connues à partir de `price_history`,
qui conserve 90 jours d'actualisations : de quoi démarrer tout de suite.

Deux limites, assumées :

  * seules les journées où les cours ont effectivement été actualisés sont
    reconstituées — un week-end, ou une semaine sans que le serveur tourne,
    reste un trou, et les mesures de risque le signalent plutôt que de le
    combler par interpolation ;
  * le taux de change n'est pas historisé par position : les lignes
    reconstituées portent le taux du jour de l'amorçage. Pour une position en
    euros c'est exact ; pour une position en devise, la variation du change
    manque sur la période reconstituée.

Une clôture déjà enregistrée n'est jamais réécrite : relancer le script ne
change rien, et il peut être lancé sans risque sur une base en service.

Usage :
  python scripts/amorcer_clotures.py
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from backend.db import get_db, init_db          # noqa: E402
from backend.positions import amorcer_clotures  # noqa: E402


def main():
    init_db(signaler_ancienne=False)

    with get_db() as db:
        avant = db.execute("SELECT COUNT(*) n FROM cours_quotidiens").fetchone()["n"]
        disponibles = db.execute(
            "SELECT COUNT(DISTINCT substr(ts, 1, 10)) n FROM price_history"
        ).fetchone()["n"]

    if not disponibles:
        print("Aucune actualisation de cours en base : rien à reconstituer.")
        print("Les clôtures se rempliront d'elles-mêmes à chaque actualisation.")
        return 0

    ajoutees, positions = amorcer_clotures()

    with get_db() as db:
        jours = db.execute(
            "SELECT COUNT(DISTINCT date) n FROM cours_quotidiens"
        ).fetchone()["n"]

    print(f"{disponibles} journée(s) d'actualisations trouvée(s) dans price_history.")
    print(f"{ajoutees} clôture(s) ajoutée(s) sur {positions} position(s)"
          f" — {avant} clôture(s) étaient déjà enregistrées, et n'ont pas bougé.")
    print(f"La série couvre maintenant {jours} journée(s) distincte(s).")

    if jours < 20:
        print("\nIl en faut une vingtaine pour que la contribution au risque et le bêta "
              "s'affichent : laissez tourner l'actualisation quotidienne, ils "
              "apparaîtront d'eux-mêmes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
