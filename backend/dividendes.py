"""CRUD des dividendes et calcul du TRI (XIRR) par position."""
import datetime

from backend.db import get_db


class DividendeError(ValueError):
    """Erreur de validation renvoyée telle quelle au client (HTTP 400)."""


def _valide(payload):
    date = (payload.get("date") or "").strip()
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise DividendeError("La date de versement doit être au format AAAA-MM-JJ.")

    nom = (payload.get("nom") or "").strip()
    if not nom:
        raise DividendeError("Le nom de la position est obligatoire.")

    try:
        account_id = int(payload.get("account_id"))
    except (TypeError, ValueError):
        raise DividendeError("Le compte est obligatoire.")

    try:
        montant = float(payload.get("montant"))
    except (TypeError, ValueError):
        raise DividendeError("Le montant brut est obligatoire.")

    montant_net = payload.get("montant_net")
    try:
        montant_net = float(montant_net) if montant_net not in (None, "") else None
    except (TypeError, ValueError):
        montant_net = None

    return date, account_id, nom[:120], montant, montant_net, (payload.get("note") or "").strip()[:200]


def get_dividendes(filters=None):
    filters = filters or {}
    where, params = [], []
    if filters.get("account_id"):
        where.append("d.account_id=?")
        params.append(int(filters["account_id"]))
    if filters.get("nom"):
        where.append("d.nom=?")
        params.append(filters["nom"])
    if filters.get("annee"):
        where.append("strftime('%Y', d.date)=?")
        params.append(str(filters["annee"]))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with get_db() as db:
        rows = db.execute(f"""
            SELECT d.*, a.nom compte, a.type compte_type
            FROM dividendes d LEFT JOIN accounts a ON a.id = d.account_id
            {clause} ORDER BY d.date DESC
        """, params).fetchall()

        stats = db.execute("""
            SELECT COUNT(*)                            nb,
                   ROUND(SUM(montant), 2)              total_brut,
                   ROUND(SUM(montant_net), 2)          total_net,
                   ROUND(SUM(CASE WHEN strftime('%Y', date) = strftime('%Y','now')
                                  THEN montant ELSE 0 END), 2) annee_en_cours,
                   MIN(date) premier_versement,
                   MAX(date) dernier_versement
            FROM dividendes
        """).fetchone()

        by_year = db.execute("""
            SELECT strftime('%Y', date) annee,
                   ROUND(SUM(montant), 2) total_brut,
                   ROUND(SUM(montant_net), 2) total_net,
                   COUNT(*) nb
            FROM dividendes GROUP BY annee ORDER BY annee DESC
        """).fetchall()

        by_pos = db.execute("""
            SELECT d.nom, d.account_id, a.nom compte, a.type compte_type,
                   ROUND(SUM(d.montant), 2) total, COUNT(*) nb
            FROM dividendes d LEFT JOIN accounts a ON a.id = d.account_id
            GROUP BY d.nom, d.account_id
            ORDER BY total DESC LIMIT 10
        """).fetchall()

        by_month = db.execute("""
            SELECT strftime('%Y-%m', date) mois, ROUND(SUM(montant), 2) total
            FROM dividendes
            WHERE date >= date('now','-12 months')
            GROUP BY mois ORDER BY mois ASC
        """).fetchall()

    return {
        "dividendes": [dict(r) for r in rows],
        "stats": dict(stats) if stats else {},
        "by_year": [dict(r) for r in by_year],
        "by_pos": [dict(r) for r in by_pos],
        "by_month": [dict(r) for r in by_month],
    }


def add_dividende(payload):
    date, account_id, nom, montant, montant_net, note = _valide(payload)
    with get_db() as db:
        if not db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise DividendeError("Compte introuvable.")
        cur = db.execute("""
            INSERT INTO dividendes (date, account_id, nom, montant, montant_net, note)
            VALUES (?,?,?,?,?,?)
        """, (date, account_id, nom, montant, montant_net, note))
        return cur.lastrowid


def update_dividende(dividende_id, payload):
    date, account_id, nom, montant, montant_net, note = _valide(payload)
    with get_db() as db:
        cur = db.execute("""
            UPDATE dividendes
            SET date=?, account_id=?, nom=?, montant=?, montant_net=?, note=?
            WHERE id=?
        """, (date, account_id, nom, montant, montant_net, note, dividende_id))
        if cur.rowcount == 0:
            raise DividendeError("Dividende introuvable.")


def delete_dividende(dividende_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM dividendes WHERE id=?", (dividende_id,))
        if cur.rowcount == 0:
            raise DividendeError("Dividende introuvable.")


def compute_tri(nom, account_id):
    """
    TRI (taux de rendement interne) d'une position :
    flux = [-investissement initial, +dividendes perçus, +valeur actuelle].
    Résolution par Newton-Raphson sur les flux datés (XIRR simplifié).
    """
    with get_db() as db:
        pos = db.execute(
            "SELECT pru, quantite, valorisation, taux_change FROM positions "
            "WHERE nom=? AND account_id=?",
            (nom, account_id),
        ).fetchone()
        divs = db.execute(
            "SELECT date, montant FROM dividendes WHERE nom=? AND account_id=? ORDER BY date ASC",
            (nom, account_id),
        ).fetchall()

    if not pos or not pos["pru"] or not pos["quantite"]:
        return None

    investi = pos["pru"] * pos["quantite"] * (pos["taux_change"] or 1.0)
    valeur = pos["valorisation"]
    aujourdhui = datetime.date.today()

    if divs:
        date_investissement = datetime.date.fromisoformat(divs[0]["date"]) - datetime.timedelta(days=1)
    else:
        date_investissement = aujourdhui - datetime.timedelta(days=365)

    flux = [(date_investissement, -investi)]
    flux += [(datetime.date.fromisoformat(d["date"]), d["montant"]) for d in divs]
    flux.append((aujourdhui, valeur))

    def xnpv(taux, flux):
        t0 = flux[0][0]
        return sum(montant / (1 + taux) ** ((date - t0).days / 365.0) for date, montant in flux)

    def xirr(flux, depart=0.1):
        taux = depart
        for _ in range(200):
            npv = xnpv(taux, flux)
            derivee = (xnpv(taux + 1e-6, flux) - npv) / 1e-6
            if abs(derivee) < 1e-12:
                break
            suivant = taux - npv / derivee
            if abs(suivant - taux) < 1e-8:
                return suivant
            taux = suivant
        return taux

    try:
        return round(xirr(flux) * 100, 2)
    except Exception:
        return None
