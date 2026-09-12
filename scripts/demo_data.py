#!/usr/bin/env python3
"""Crée un portefeuille de démonstration (données fictives) pour découvrir l'interface.

Utile pour voir à quoi ressemblent les onglets avant d'y saisir ses vrais comptes.

Usage :
  python scripts/demo_data.py            # ajoute les comptes de démonstration
  python scripts/demo_data.py --reset    # supprime d'abord tous les comptes existants
"""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.accounts import create_account, list_accounts, delete_account  # noqa: E402
from backend.db import get_db, init_db  # noqa: E402
from backend.positions import create_position, load_portfolio, record_history  # noqa: E402
from backend.dividendes import add_dividende  # noqa: E402
from backend.fi import save_reglages  # noqa: E402
from backend.rebalancing import save_cibles_classes  # noqa: E402
from backend.transactions import add_transaction  # noqa: E402

COMPTES = [
    {
        "compte": {"nom": "PEA", "type": "pea", "etablissement": "Courtier en ligne",
                   "date_ouverture": "2018-03-15", "cible_pct": 35},
        "positions": [
            {"nom": "Danone", "ticker": "BN.PA", "isin": "FR0000120644", "secteur": "Consommation", "zone": "Europe", "classe": "actions", "quantite": 25, "pru": 58.20, "cours": 68.40},
            {"nom": "Michelin", "ticker": "ML.PA", "isin": "FR001400AJ45", "secteur": "Industrie", "zone": "Europe", "classe": "actions", "quantite": 40, "pru": 28.10, "cours": 34.35},
            {"nom": "ETF MSCI World", "ticker": "IWDA.AS", "secteur": "ETF diversifié", "zone": "Monde", "classe": "actions", "groupe": "MSCI World", "ter": 0.20, "quantite": 120, "pru": 78.30, "cours": 96.10},
        ],
    },
    {
        "compte": {"nom": "Compte-titres", "type": "cto", "etablissement": "Courtier international",
                   "date_ouverture": "2021-06-01", "cible_pct": 20},
        "positions": [
            {"nom": "Microsoft", "ticker": "MSFT", "secteur": "Technologie", "zone": "États-Unis", "classe": "actions", "quantite": 12, "pru": 310.00, "cours": 425.50, "devise": "USD", "taux_change": 0.9238},
            {"nom": "Johnson & Johnson", "ticker": "JNJ", "secteur": "Santé", "zone": "États-Unis", "classe": "actions", "quantite": 15, "pru": 152.00, "cours": 163.40, "devise": "USD", "taux_change": 0.9238},
        ],
    },
    {
        "compte": {"nom": "Assurance vie", "type": "av", "etablissement": "Assureur",
                   "date_ouverture": "2019-11-04", "cible_pct": 20, "frais_pct": 0.60},
        "positions": [
            {"nom": "Fonds euros", "secteur": "Fonds euros", "zone": "Europe", "classe": "obligations", "quantite": 1, "pru": 18000, "cours": 19450},
            {"nom": "ETF actions monde", "ticker": "IWDA.AS", "secteur": "ETF diversifié", "zone": "Monde", "classe": "actions", "groupe": "MSCI World", "ter": 0.20, "quantite": 45, "pru": 78.30, "cours": 96.10},
        ],
    },
    {
        "compte": {"nom": "PER individuel", "type": "per", "etablissement": "Gestionnaire",
                   "date_ouverture": "2022-01-10", "cible_pct": 15, "frais_pct": 0.80},
        "positions": [
            {"nom": "Fonds actions Europe", "secteur": "Actions Europe", "zone": "Europe", "classe": "actions", "ter": 1.10, "quantite": 120, "pru": 52.40, "cours": 58.90},
        ],
    },
    {
        "compte": {"nom": "Cryptomonnaies", "type": "crypto", "etablissement": "Plateforme d'échange",
                   "date_ouverture": "2023-02-20", "cible_pct": 5},
        "positions": [
            {"nom": "Bitcoin", "ticker": "BTC-EUR", "secteur": "Actifs numériques", "zone": "Décentralisé", "classe": "crypto", "quantite": 0.085, "pru": 32000, "cours": 61500},
            {"nom": "Ethereum", "ticker": "ETH-EUR", "secteur": "Actifs numériques", "zone": "Décentralisé", "classe": "crypto", "quantite": 1.4, "pru": 1850, "cours": 2740},
        ],
    },
    {
        "compte": {"nom": "Livret A", "type": "liquidites", "etablissement": "Banque",
                   "date_ouverture": "2016-01-05"},
        "positions": [
            {"nom": "Livret A", "secteur": "Liquidités", "zone": "Europe", "classe": "monetaire", "quantite": 1, "pru": 18000, "cours": 18500},
        ],
    },
    {
        "compte": {"nom": "Résidence principale", "type": "immobilier", "etablissement": "Bien détenu en direct",
                   "date_ouverture": "2017-09-20"},
        "positions": [
            {"nom": "Appartement", "secteur": "Immobilier", "zone": "Europe", "classe": "immobilier", "quantite": 1, "pru": 265000, "cours": 320000},
        ],
    },
    {
        "compte": {"nom": "Crédit immobilier", "type": "credit", "etablissement": "Banque prêteuse",
                   "date_ouverture": "2017-09-20"},
        "positions": [
            {"nom": "Capital restant dû", "secteur": "", "zone": "", "quantite": 1, "pru": 212000, "cours": 166500},
        ],
    },
    {
        "compte": {"nom": "Métaux précieux", "type": "metaux", "etablissement": "Coffre",
                   "date_ouverture": "2020-09-12", "cible_pct": 5},
        "positions": [
            {"nom": "Or", "ticker": "GC=F", "secteur": "Métaux précieux", "zone": "Monde", "classe": "or", "quantite": 3, "pru": 1720, "cours": 2380, "devise": "USD", "taux_change": 0.9238},
        ],
    },
]


# Journal de démonstration, rattaché aux positions par leur nom.
#
# Microsoft montre l'intérêt du prix de revient figé : acheté quand l'euro
# valait 1,20 dollar, il a coûté 3 100 € — et non les 3 436 € qu'un recalcul au
# taux du jour ferait apparaître. Danone montre une plus-value réalisée : 30
# titres achetés, 5 revendus, 25 encore en portefeuille.
MOUVEMENTS = [
    ("PEA", "Danone", {"date": "2019-05-14", "type": "achat", "quantite": 30, "prix": 58.20, "frais": 5}),
    ("PEA", "Danone", {"date": "2023-09-08", "type": "vente", "quantite": 5, "prix": 71.40, "frais": 5}),
    ("PEA", "Michelin", {"date": "2020-02-10", "type": "achat", "quantite": 40, "prix": 28.10, "frais": 5}),
    ("PEA", "ETF MSCI World", {"date": "2021-03-02", "type": "achat", "quantite": 120, "prix": 78.30, "frais": 8}),
    ("Compte-titres", "Microsoft", {"date": "2021-07-20", "type": "achat", "quantite": 12,
                                    "prix": 310.00, "devise": "USD", "taux_change": 0.8333, "frais": 9}),
    ("Compte-titres", "Johnson & Johnson", {"date": "2022-04-11", "type": "achat", "quantite": 15,
                                            "prix": 152.00, "devise": "USD", "taux_change": 0.9100, "frais": 9}),
    ("Cryptomonnaies", "Bitcoin", {"date": "2023-03-05", "type": "achat", "quantite": 0.085, "prix": 32000}),
    ("Cryptomonnaies", "Ethereum", {"date": "2023-06-18", "type": "achat", "quantite": 1.4, "prix": 1850}),
    ("Assurance vie", None, {"date": "2019-11-04", "type": "versement", "montant": 15000}),
    ("Assurance vie", None, {"date": "2022-05-10", "type": "versement", "montant": 6500}),
    ("Assurance vie", None, {"date": "2025-01-15", "type": "frais", "montant": 148}),
    ("PER individuel", None, {"date": "2022-01-10", "type": "versement", "montant": 6288}),
]


# Deux ans de dividendes, pour que les rendements de l'onglet Dividendes aient
# de quoi se calculer : 12 mois glissants comparés aux 12 précédents.
DIVIDENDES = [
    ("PEA", "Danone", [(30, 51.0, 51.0), (120, 49.5, 49.5), (210, 48.0, 48.0),
                       (300, 47.0, 47.0), (395, 45.5, 45.5), (480, 44.0, 44.0)]),
    ("PEA", "Michelin", [(75, 52.0, 52.0), (440, 48.0, 48.0)]),
    ("Compte-titres", "Microsoft", [(35, 9.6, 6.7), (125, 9.4, 6.6),
                                    (215, 9.0, 6.3), (305, 8.8, 6.2),
                                    (400, 8.4, 5.9), (490, 8.0, 5.6)]),
    ("Compte-titres", "Johnson & Johnson", [(60, 18.5, 12.9), (150, 18.5, 12.9),
                                            (245, 17.8, 12.5), (425, 17.0, 11.9)]),
]


def creer_dividendes(comptes_par_nom):
    """Versements de démonstration, datés en jours avant aujourd'hui."""
    aujourdhui = datetime.date.today()
    cree = 0
    for nom_compte, nom_position, versements in DIVIDENDES:
        compte = comptes_par_nom.get(nom_compte)
        if not compte:
            continue
        for jours, brut, net in versements:
            add_dividende({
                "date": (aujourdhui - datetime.timedelta(days=jours)).isoformat(),
                "account_id": compte["id"], "nom": nom_position,
                "montant": brut, "montant_net": net,
            })
            cree += 1
    return cree


def creer_mouvements(comptes_par_nom):
    """Alimente le journal, d'où sont recalculés PMP et prix de revient."""
    cree = 0
    for nom_compte, nom_position, mouvement in MOUVEMENTS:
        compte = comptes_par_nom.get(nom_compte)
        if not compte:
            continue
        payload = {**mouvement, "account_id": compte["id"]}
        if nom_position:
            position = next((p for p in compte["positions"] if p["nom"] == nom_position), None)
            if not position:
                continue
            payload["position_id"] = position["id"]
        add_transaction(payload)
        cree += 1
    return cree


def reset():
    for compte in list_accounts():
        delete_account(compte["id"])
    with get_db() as db:
        db.execute("DELETE FROM history_daily")
        db.execute("DELETE FROM history_intraday")
        db.execute("DELETE FROM dividendes")
        db.execute("DELETE FROM transactions")
        db.execute("DELETE FROM allocations_classes")
        db.execute("DELETE FROM reglages")
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

    comptes_par_nom = {c["nom"]: c for c in load_portfolio()["accounts"]}
    print(f"  Journal : {creer_mouvements(comptes_par_nom)} mouvement(s)")
    print(f"  Dividendes : {creer_dividendes(comptes_par_nom)} versement(s)")

    save_cibles_classes({"actions": 60, "obligations": 25, "or": 10, "crypto": 5})
    save_reglages({"depenses_annuelles": 32000, "epargne_mensuelle": 1400,
                   "taux_retrait": 4, "rendement_reel": 5, "horizon_ans": 20})
    print("  Profil : 32 000 €/an de dépenses visées, 1 400 €/mois d'épargne")
    print("  Allocation cible : actions 60 %, obligations 25 %, or 10 %, crypto 5 %")

    record_history()
    print("\nPortefeuille de démonstration créé (données fictives).")
    print("Lancez « python app.py » puis actualisez les cours pour voir les prix réels des tickers.")


if __name__ == "__main__":
    main()
