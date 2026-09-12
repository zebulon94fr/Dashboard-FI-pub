"""CRUD des dividendes et revenus encaissés."""
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


# Le TRI vit désormais dans performance.py : il se calcule sur les flux datés du
# journal des mouvements, et non plus sur une date d'achat reconstituée.
