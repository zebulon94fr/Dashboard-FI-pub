"""Mesures de performance : TWR, TRI et flux externes.

Deux mesures, deux questions, et il faut les deux :

  * le **TWR** (rendement pondéré par le temps) neutralise les versements en
    chaînant les rendements entre chaque flux. C'est la performance du
    portefeuille, la seule comparable à un indice ;
  * le **TRI** (rendement pondéré par les montants, ou XIRR) tient compte de la
    date et de la taille de chaque versement. C'est la performance de
    l'investisseur, celle qui récompense ou sanctionne le moment d'entrée.

Sans journal de mouvements, les deux sont impossibles à calculer : une courbe
de valorisation ne sait pas distinguer un gain d'un apport. C'est pourquoi
`transactions` est le socle de tout ce module.

Convention de signe des flux : `+` quand de l'argent entre dans le portefeuille
(achat, versement), `-` quand il en sort (vente, retrait, frais, dividende
encaissé). Un dividende quitte le périmètre suivi : le compter comme une sortie
fait du TWR un rendement total, dividendes inclus, plutôt qu'une perte apparente.
"""
import datetime

from backend.db import get_db
from catalog import TYPES_TRANSACTION


# ══════════════════════════════════════════════════════════════
# FLUX EXTERNES
# ══════════════════════════════════════════════════════════════
def flux_externes(account_id=None, depuis=None):
    """
    Flux datés du portefeuille : [(date, montant signé)], du plus ancien au plus récent.

    Agrège le journal des mouvements et les dividendes encaissés.
    """
    conditions_tx, params_tx = [], []
    conditions_div, params_div = [], []
    if account_id:
        conditions_tx.append("account_id=?")
        params_tx.append(int(account_id))
        conditions_div.append("account_id=?")
        params_div.append(int(account_id))
    if depuis:
        conditions_tx.append("date >= ?")
        params_tx.append(depuis)
        conditions_div.append("date >= ?")
        params_div.append(depuis)

    ou_tx = ("WHERE " + " AND ".join(conditions_tx)) if conditions_tx else ""
    ou_div = ("WHERE " + " AND ".join(conditions_div)) if conditions_div else ""

    with get_db() as db:
        mouvements = db.execute(
            f"SELECT date, type, montant_eur FROM transactions {ou_tx}", params_tx
        ).fetchall()
        dividendes = db.execute(
            f"SELECT date, montant FROM dividendes {ou_div}", params_div
        ).fetchall()

    flux = [
        (m["date"], TYPES_TRANSACTION[m["type"]]["sens"] * (m["montant_eur"] or 0))
        for m in mouvements if m["type"] in TYPES_TRANSACTION
    ]
    # Un dividende encaissé sort du périmètre valorisé : c'est un flux sortant.
    flux += [(d["date"], -(d["montant"] or 0)) for d in dividendes]
    flux.sort(key=lambda f: f[0])
    return flux


def flux_par_date(account_id=None, depuis=None):
    """Flux externes cumulés par jour : {date: montant net}."""
    par_jour = {}
    for date, montant in flux_externes(account_id, depuis):
        par_jour[date] = par_jour.get(date, 0.0) + montant
    return par_jour


# ══════════════════════════════════════════════════════════════
# TWR
# ══════════════════════════════════════════════════════════════
def compute_twr(period_days=365, account_id=0):
    """
    Rendement pondéré par le temps, en base 100.

    Le rendement de chaque sous-période vaut (V_fin - flux) / V_début - 1, puis
    ces rendements sont chaînés. Un versement fait monter la valorisation sans
    faire monter l'indice : c'est exactement ce qui manquait à la comparaison
    de l'onglet Historique.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=period_days)).isoformat()

    with get_db() as db:
        historique = db.execute("""
            SELECT date, valorisation FROM history_daily
            WHERE account_id = ? AND date >= ? ORDER BY date ASC
        """, (account_id, cutoff)).fetchall()

    if len(historique) < 2:
        return {
            "base100": [], "twr": None, "flux_total": 0.0,
            "message": "Deux journées d'historique au minimum sont nécessaires — "
                       "actualisez les cours quelques jours.",
        }

    flux = flux_par_date(account_id or None, cutoff)

    base = 100.0
    serie = [{"date": historique[0]["date"], "valeur": round(base, 4)}]
    precedent = historique[0]["valorisation"]

    for ligne in historique[1:]:
        courant = ligne["valorisation"]
        apport = flux.get(ligne["date"], 0.0)
        if precedent > 0:
            rendement = (courant - apport) / precedent - 1
            # Un rendement sous -100 % n'a pas de sens : c'est le signe d'un flux
            # mal daté, pas d'une perte. On neutralise la sous-période.
            if rendement > -1:
                base *= (1 + rendement)
        serie.append({"date": ligne["date"], "valeur": round(base, 4)})
        precedent = courant

    return {
        "base100": serie,
        "twr": round(base / 100 - 1, 6),
        "flux_total": round(sum(flux.values()), 2),
        "date_debut": historique[0]["date"],
        "message": None if any(flux.values()) else
                   "Aucun mouvement enregistré sur la période : le TWR se confond "
                   "avec la variation de la valorisation.",
    }


# ══════════════════════════════════════════════════════════════
# TRI (XIRR)
# ══════════════════════════════════════════════════════════════
def xnpv(taux, flux):
    """Valeur actuelle nette de flux datés, actualisés au taux annuel `taux`."""
    t0 = flux[0][0]
    return sum(montant / (1 + taux) ** ((date - t0).days / 365.0) for date, montant in flux)


def xirr(flux, precision=1e-9):
    """
    Taux de rendement interne de flux datés, ou None s'il n'existe pas.

    Résolution par bissection : la convergence est garantie une fois la racine
    encadrée, là où Newton-Raphson seul peut diverger et renvoyer en silence un
    taux qui n'annule rien. Renvoyer None vaut mieux qu'un TRI faux.
    """
    if len(flux) < 2:
        return None
    if not (any(m > 0 for _, m in flux) and any(m < 0 for _, m in flux)):
        return None                      # sans flux de signes opposés, pas de racine

    bas, haut = -0.9999, 10.0
    f_bas, f_haut = xnpv(bas, flux), xnpv(haut, flux)
    if f_bas * f_haut > 0:
        return None                      # racine hors de l'intervalle exploré

    for _ in range(300):
        milieu = (bas + haut) / 2
        f_milieu = xnpv(milieu, flux)
        if abs(f_milieu) < 1e-6 or (haut - bas) < precision:
            return milieu
        if f_bas * f_milieu < 0:
            haut = milieu
        else:
            bas, f_bas = milieu, f_milieu
    return (bas + haut) / 2


def _flux_investisseur(mouvements, dividendes, valeur_actuelle):
    """
    Flux du point de vue de l'investisseur : ce qu'il sort de sa poche est
    négatif, ce qu'il encaisse est positif, et la valeur actuelle clôture.
    """
    flux = []
    for date, montant in mouvements:
        flux.append((datetime.date.fromisoformat(date), -montant))
    for date, montant in dividendes:
        flux.append((datetime.date.fromisoformat(date), montant))
    flux.sort(key=lambda f: f[0])

    aujourdhui = datetime.date.today()
    if valeur_actuelle:
        flux.append((aujourdhui, valeur_actuelle))
    return flux


def compute_tri(nom, account_id):
    """
    TRI d'une position, reconstitué depuis son journal de mouvements.

    Sans journal, aucune date d'achat n'est connue : le TRI est alors refusé
    plutôt qu'estimé sur une date inventée, qui donnait des taux à trois
    chiffres sur les lignes détenues de longue date.
    """
    with get_db() as db:
        position = db.execute(
            "SELECT id, valorisation FROM positions WHERE nom=? AND account_id=?",
            (nom, account_id),
        ).fetchone()

        mouvements = db.execute("""
            SELECT date, type, montant_eur FROM transactions
            WHERE account_id=? AND nom=? AND type IN ('achat','vente')
            ORDER BY date ASC
        """, (account_id, nom)).fetchall()

        dividendes = db.execute(
            "SELECT date, montant FROM dividendes WHERE nom=? AND account_id=? ORDER BY date ASC",
            (nom, account_id),
        ).fetchall()

    if not mouvements:
        return {
            "tri": None, "methode": None,
            "message": "Aucun mouvement enregistré pour cette ligne — "
                       "saisissez ses achats pour obtenir un TRI daté.",
        }

    flux_portefeuille = [
        (m["date"], TYPES_TRANSACTION[m["type"]]["sens"] * (m["montant_eur"] or 0))
        for m in mouvements
    ]
    flux = _flux_investisseur(
        flux_portefeuille,
        [(d["date"], d["montant"] or 0) for d in dividendes],
        position["valorisation"] if position else 0,
    )

    taux = xirr(flux)
    if taux is None:
        return {
            "tri": None, "methode": "journal",
            "message": "Les flux enregistrés ne permettent pas de calculer un TRI "
                       "(pas de changement de signe).",
        }
    return {
        "tri": round(taux * 100, 2), "methode": "journal",
        "depuis": flux[0][0].isoformat(), "nb_flux": len(flux), "message": None,
    }


def compute_tri_portefeuille(account_id=None):
    """TRI de l'ensemble du portefeuille, ou d'une enveloppe."""
    with get_db() as db:
        if account_id:
            total = db.execute(
                "SELECT COALESCE(SUM(valorisation), 0) v FROM positions WHERE account_id=?",
                (int(account_id),),
            ).fetchone()["v"]
        else:
            total = db.execute(
                "SELECT COALESCE(SUM(valorisation), 0) v FROM positions"
            ).fetchone()["v"]

    mouvements = flux_externes(account_id)
    if not mouvements:
        return {
            "tri": None, "message": "Aucun mouvement enregistré — "
                                    "le TRI a besoin de versements datés.",
        }

    taux = xirr(_flux_investisseur(mouvements, [], total))
    return {
        "tri": round(taux * 100, 2) if taux is not None else None,
        "depuis": mouvements[0][0],
        "nb_flux": len(mouvements) + 1,
        "message": None if taux is not None else
                   "Les flux enregistrés ne permettent pas de calculer un TRI.",
    }
