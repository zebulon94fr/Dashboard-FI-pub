#!/usr/bin/env python3
"""Crée un portefeuille de démonstration (données fictives) pour découvrir l'interface.

Utile pour voir à quoi ressemblent les onglets avant d'y saisir ses vrais comptes.

Usage :
  python scripts/demo_data.py            # ajoute les comptes de démonstration
  python scripts/demo_data.py --reset    # supprime d'abord tous les comptes existants
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.accounts import create_account, list_accounts, delete_account  # noqa: E402
from backend.db import get_db, init_db  # noqa: E402
from backend.positions import create_position, record_history  # noqa: E402

COMPTES = [
    {
        "compte": {"nom": "PEA", "type": "pea", "etablissement": "Courtier en ligne",
                   "date_ouverture": "2018-03-15", "cible_pct": 35},
        "positions": [
            {"nom": "Air Liquide", "ticker": "AI.PA", "isin": "FR0000120073", "secteur": "Industrie", "zone": "Europe", "quantite": 25, "pru": 148.20, "cours": 168.40},
            {"nom": "Sanofi", "ticker": "SAN.PA", "isin": "FR0000120578", "secteur": "Santé", "zone": "Europe", "quantite": 40, "pru": 88.10, "cours": 94.35},
            {"nom": "Amundi MSCI World UCITS ETF", "ticker": "CW8.PA", "secteur": "ETF diversifié", "zone": "Monde", "quantite": 30, "pru": 420.00, "cours": 498.70},
        ],
    },
    {
        "compte": {"nom": "Compte-titres", "type": "cto", "etablissement": "Courtier international",
                   "date_ouverture": "2021-06-01", "cible_pct": 20},
        "positions": [
            {"nom": "Microsoft", "ticker": "MSFT", "secteur": "Technologie", "zone": "États-Unis", "quantite": 12, "pru": 310.00, "cours": 425.50, "devise": "USD"},
            {"nom": "Air Products", "ticker": "APD", "secteur": "Industrie", "zone": "États-Unis", "quantite": 8, "pru": 265.00, "cours": 288.20, "devise": "USD"},
        ],
    },
    {
        "compte": {"nom": "Assurance vie", "type": "av", "etablissement": "Assureur",
                   "date_ouverture": "2019-11-04", "cible_pct": 20},
        "positions": [
            {"nom": "Fonds euros", "secteur": "Fonds euros", "zone": "Europe", "quantite": 1, "pru": 18000, "cours": 19450},
            {"nom": "ETF actions monde", "ticker": "IWDA.AS", "secteur": "ETF diversifié", "zone": "Monde", "quantite": 45, "pru": 78.30, "cours": 96.10},
        ],
    },
    {
        "compte": {"nom": "PER individuel", "type": "per", "etablissement": "Gestionnaire",
                   "date_ouverture": "2022-01-10", "cible_pct": 15},
        "positions": [
            {"nom": "Fonds actions Europe", "secteur": "Actions Europe", "zone": "Europe", "quantite": 120, "pru": 52.40, "cours": 58.90},
        ],
    },
    {
        "compte": {"nom": "Cryptomonnaies", "type": "crypto", "etablissement": "Plateforme d'échange",
                   "date_ouverture": "2023-02-20", "cible_pct": 5},
        "positions": [
            {"nom": "Bitcoin", "ticker": "BTC-EUR", "secteur": "Actifs numériques", "zone": "Décentralisé", "quantite": 0.085, "pru": 32000, "cours": 61500},
            {"nom": "Ethereum", "ticker": "ETH-EUR", "secteur": "Actifs numériques", "zone": "Décentralisé", "quantite": 1.4, "pru": 1850, "cours": 2740},
        ],
    },
    {
        "compte": {"nom": "Métaux précieux", "type": "metaux", "etablissement": "Coffre",
                   "date_ouverture": "2020-09-12", "cible_pct": 5},
        "positions": [
            {"nom": "Or", "ticker": "GC=F", "secteur": "Métaux précieux", "zone": "Monde", "quantite": 3, "pru": 1720, "cours": 2380, "devise": "USD"},
        ],
    },
]


def reset():
    for compte in list_accounts():
        delete_account(compte["id"])
    with get_db() as db:
        db.execute("DELETE FROM history_daily")
        db.execute("DELETE FROM history_intraday")
        db.execute("DELETE FROM dividendes")
    print("Comptes existants supprimés.")


def main():
    init_db()
    if "--reset" in sys.argv:
        reset()
    elif list_accounts():
        print("La base contient déjà des comptes — relancez avec --reset pour repartir de zéro.")
        sys.exit(1)

    for entree in COMPTES:
        account_id = create_account(entree["compte"])
        for position in entree["positions"]:
            create_position(account_id, position)
        print(f"  {entree['compte']['nom']} : {len(entree['positions'])} position(s)")

    record_history()
    print("\nPortefeuille de démonstration créé (données fictives).")
    print("Lancez « python app.py » puis actualisez les cours pour voir les prix réels des tickers.")


if __name__ == "__main__":
    main()
