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


def rendements():
    """
    Rendements des dividendes, par ligne et pour l'ensemble du portefeuille.

    Additionner des versements ne dit rien tant qu'on ne les rapporte pas à un
    capital. Trois rapports différents, trois questions différentes :

      * le **rendement courant** (12 mois glissants / valorisation) dit ce que la
        ligne sert aujourd'hui, au prix où elle cote ;
      * le **rendement sur prix de revient** rapporte les mêmes versements à ce
        qu'on a réellement payé. C'est lui qui récompense la détention longue,
        et il n'apparaît nulle part ailleurs dans le dashboard ;
      * le **taux de prélèvement effectif** (1 - net/brut) rend enfin utile la
        saisie du montant net, et montre ce que coûte le logement d'une ligne
        sur un compte-titres plutôt que sur un PEA.
    """
    with get_db() as db:
        lignes = db.execute("""
            SELECT d.nom, d.account_id, a.nom compte, a.type compte_type,
                   ROUND(SUM(CASE WHEN d.date >= date('now','-12 months')
                                  THEN d.montant ELSE 0 END), 2) ttm_brut,
                   ROUND(SUM(CASE WHEN d.date >= date('now','-12 months')
                                  THEN COALESCE(d.montant_net, 0) ELSE 0 END), 2) ttm_net,
                   ROUND(SUM(CASE WHEN d.date >= date('now','-12 months')
                                       AND d.montant_net IS NOT NULL
                                  THEN d.montant ELSE 0 END), 2) ttm_brut_avec_net,
                   ROUND(SUM(CASE WHEN d.date >= date('now','-24 months')
                                       AND d.date < date('now','-12 months')
                                  THEN d.montant ELSE 0 END), 2) precedent_brut,
                   COUNT(*) nb
            FROM dividendes d LEFT JOIN accounts a ON a.id = d.account_id
            GROUP BY d.nom, d.account_id
        """).fetchall()

        positions = {
            (p["nom"], p["account_id"]): p for p in db.execute("""
                SELECT nom, account_id, valorisation,
                       COALESCE(cout_eur, pru * quantite * taux_change) cout
                FROM positions
            """).fetchall()
        }

    resultats = []
    for ligne in lignes:
        position = positions.get((ligne["nom"], ligne["account_id"]))
        valorisation = position["valorisation"] if position else 0
        cout = (position["cout"] if position else 0) or 0
        ttm = ligne["ttm_brut"] or 0
        precedent = ligne["precedent_brut"] or 0

        resultats.append({
            "nom": ligne["nom"], "compte": ligne["compte"], "compte_type": ligne["compte_type"],
            "account_id": ligne["account_id"], "nb": ligne["nb"],
            "ttm_brut": ttm,
            "ttm_net": ligne["ttm_net"] or 0,
            "valorisation": round(valorisation, 2),
            "cout": round(cout, 2),
            "rendement_courant": round(ttm / valorisation, 6) if valorisation else None,
            "rendement_sur_revient": round(ttm / cout, 6) if cout else None,
            # Le taux de prélèvement ne vaut que sur les versements dont le net
            # est renseigné : le comparer au brut total le sous-estimerait.
            "taux_prelevement": round(1 - (ligne["ttm_net"] / ligne["ttm_brut_avec_net"]), 6)
                                if ligne["ttm_brut_avec_net"] else None,
            "croissance": round(ttm / precedent - 1, 6) if precedent else None,
            "position_connue": position is not None,
        })

    resultats.sort(key=lambda r: r["ttm_brut"], reverse=True)

    total_ttm = sum(r["ttm_brut"] for r in resultats)
    total_net = sum(r["ttm_net"] for r in resultats)
    total_valorisation = sum(r["valorisation"] for r in resultats if r["position_connue"])
    total_cout = sum(r["cout"] for r in resultats if r["position_connue"])
    precedent_total = sum(l["precedent_brut"] or 0 for l in lignes)

    return {
        "lignes": resultats,
        "total": {
            "ttm_brut": round(total_ttm, 2),
            "ttm_net": round(total_net, 2),
            "mensuel_moyen": round(total_ttm / 12, 2),
            "rendement_courant": round(total_ttm / total_valorisation, 6) if total_valorisation else None,
            "rendement_sur_revient": round(total_ttm / total_cout, 6) if total_cout else None,
            "croissance": round(total_ttm / precedent_total - 1, 6) if precedent_total else None,
            "nb_lignes": len(resultats),
        },
        "orphelines": [r["nom"] for r in resultats if not r["position_connue"]],
    }
