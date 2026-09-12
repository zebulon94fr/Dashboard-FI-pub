"""CRUD des positions, calculs dérivés et enregistrement de l'historique."""
import datetime

from backend.accounts import list_accounts
from backend.db import get_db

CHAMPS = ("nom", "ticker", "isin", "secteur", "zone",
          "quantite", "pru", "cours", "devise")


class PositionError(ValueError):
    """Erreur de validation renvoyée telle quelle au client (HTTP 400)."""


def _nombre(valeur, defaut=0.0):
    """Accepte 12.5, « 12,5 » ou « 1 234,56 » — la virgule française comprise."""
    if valeur is None or valeur == "":
        return defaut
    if isinstance(valeur, (int, float)):
        return float(valeur)
    texte = str(valeur).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(texte)
    except ValueError:
        return defaut


def _taux_connu(db, devise):
    """Dernier taux de change connu pour cette devise, sinon 1.0."""
    if devise == "EUR":
        return 1.0
    row = db.execute(
        "SELECT taux_change FROM positions WHERE devise=? AND taux_change > 0 "
        "ORDER BY updated_at DESC LIMIT 1",
        (devise,),
    ).fetchone()
    return row["taux_change"] if row else 1.0


def calculs(quantite, pru, cours, taux_change):
    """Valorisation et plus-value latente en euros, performance en décimal."""
    valorisation = cours * quantite * taux_change
    pv_latent = (cours - pru) * quantite * taux_change
    pv_pct = ((cours - pru) / pru) if pru else 0.0
    return round(valorisation, 2), round(pv_latent, 2), round(pv_pct, 6)


def _valide(payload, partiel=False):
    out = {}

    if not partiel or "nom" in payload:
        nom = (payload.get("nom") or "").strip()
        if not nom:
            raise PositionError("Le nom de la position est obligatoire.")
        out["nom"] = nom[:120]

    for champ in ("ticker", "isin", "secteur", "zone"):
        if champ in payload:
            valeur = (payload.get(champ) or "").strip()[:60]
            out[champ] = valeur.upper() if champ in ("ticker", "isin") else valeur

    for champ in ("quantite", "pru", "cours"):
        if not partiel or champ in payload:
            out[champ] = _nombre(payload.get(champ))

    if not partiel or "devise" in payload:
        out["devise"] = ((payload.get("devise") or "EUR").strip().upper() or "EUR")[:3]

    return out


def row_to_position(row):
    p = dict(row)
    p["pv_pct"] = p.get("pv_pct") or 0
    return p


def load_positions(account_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM positions WHERE account_id=? ORDER BY valorisation DESC, id",
            (account_id,),
        ).fetchall()
    return [row_to_position(r) for r in rows]


def load_portfolio(jours_historique=365):
    """Portefeuille complet : comptes, positions et historique — payload de GET /api/data."""
    comptes = list_accounts()

    with get_db() as db:
        positions = db.execute("SELECT * FROM positions ORDER BY valorisation DESC, id").fetchall()
        dernier = db.execute(
            "SELECT ts FROM history_intraday ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        cutoff = (datetime.date.today() - datetime.timedelta(days=jours_historique)).isoformat()
        historique = db.execute(
            "SELECT date, account_id, valorisation FROM history_daily "
            "WHERE date >= ? ORDER BY date ASC",
            (cutoff,),
        ).fetchall()

    par_compte = {c["id"]: [] for c in comptes}
    for row in positions:
        p = row_to_position(row)
        par_compte.setdefault(p["account_id"], []).append(p)
    for c in comptes:
        c["positions"] = par_compte.get(c["id"], [])

    # Une entrée par date : le total, plus le détail par compte.
    jours = {}
    for h in historique:
        entree = jours.setdefault(h["date"], {"date": h["date"], "total": 0, "comptes": {}})
        if h["account_id"] == 0:
            entree["total"] = h["valorisation"]
        else:
            entree["comptes"][str(h["account_id"])] = h["valorisation"]

    return {
        "accounts": comptes,
        "history": [jours[d] for d in sorted(jours)],
        "lastUpdate": dernier["ts"] if dernier else "",
    }


def create_position(account_id, payload):
    champs = _valide(payload)
    with get_db() as db:
        compte = db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not compte:
            raise PositionError("Compte introuvable — créez d'abord un compte.")
        taux = _taux_connu(db, champs["devise"])
        valo, pv, pct = calculs(champs["quantite"], champs["pru"], champs["cours"], taux)
        cur = db.execute("""
            INSERT INTO positions
              (account_id, nom, ticker, isin, secteur, zone, quantite, pru, cours,
               devise, taux_change, valorisation, pv_latent, pv_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            account_id, champs["nom"], champs.get("ticker", ""), champs.get("isin", ""),
            champs.get("secteur", ""), champs.get("zone", ""),
            champs["quantite"], champs["pru"], champs["cours"],
            champs["devise"], taux, valo, pv, pct,
        ))
        return cur.lastrowid


def update_position(position_id, payload):
    champs = _valide(payload, partiel=True)
    with get_db() as db:
        actuelle = db.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        if not actuelle:
            raise PositionError("Position introuvable.")

        fusion = {**dict(actuelle), **champs}
        taux = (_taux_connu(db, fusion["devise"])
                if fusion["devise"] != actuelle["devise"] else actuelle["taux_change"])
        valo, pv, pct = calculs(fusion["quantite"], fusion["pru"], fusion["cours"], taux)

        db.execute("""
            UPDATE positions SET
              nom=?, ticker=?, isin=?, secteur=?, zone=?, quantite=?, pru=?, cours=?,
              devise=?, taux_change=?, valorisation=?, pv_latent=?, pv_pct=?,
              updated_at=datetime('now')
            WHERE id=?
        """, (
            fusion["nom"], fusion["ticker"], fusion["isin"], fusion["secteur"], fusion["zone"],
            fusion["quantite"], fusion["pru"], fusion["cours"],
            fusion["devise"], taux, valo, pv, pct, position_id,
        ))


def move_position(position_id, account_id):
    """Rattache une position à un autre compte."""
    with get_db() as db:
        compte = db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not compte:
            raise PositionError("Compte de destination introuvable.")
        cur = db.execute("UPDATE positions SET account_id=? WHERE id=?", (account_id, position_id))
        if cur.rowcount == 0:
            raise PositionError("Position introuvable.")


def delete_position(position_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM positions WHERE id=?", (position_id,))
        if cur.rowcount == 0:
            raise PositionError("Position introuvable.")


def record_history(usd_eur=None):
    """Photographie la valorisation courante : une ligne par compte + le total."""
    aujourdhui = datetime.date.today().isoformat()
    maintenant = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with get_db() as db:
        totaux = db.execute("""
            SELECT a.id, COALESCE(SUM(p.valorisation), 0) valorisation
            FROM accounts a
            LEFT JOIN positions p ON p.account_id = a.id
            GROUP BY a.id
        """).fetchall()

        lignes = [(row["id"], round(row["valorisation"], 2)) for row in totaux]
        lignes.append((0, round(sum(v for _, v in lignes), 2)))

        for account_id, valorisation in lignes:
            db.execute("""
                INSERT INTO history_daily (date, account_id, valorisation)
                VALUES (?,?,?)
                ON CONFLICT(date, account_id) DO UPDATE SET valorisation=excluded.valorisation
            """, (aujourdhui, account_id, valorisation))
            db.execute("""
                INSERT INTO history_intraday (ts, account_id, valorisation, usd_eur)
                VALUES (?,?,?,?)
                ON CONFLICT(ts, account_id) DO UPDATE SET valorisation=excluded.valorisation
            """, (maintenant, account_id, valorisation, usd_eur))

        db.execute("DELETE FROM history_intraday WHERE ts < datetime('now','-90 days')")


def record_price_history(points, ts):
    """Enregistre le cours de chaque position après une actualisation."""
    with get_db() as db:
        for position_id, cours, variation in points:
            db.execute("""
                INSERT INTO price_history (position_id, ts, cours, variation)
                VALUES (?,?,?,?)
            """, (position_id, ts, cours, variation))

        # Même rétention que l'historique intraday : au-delà de 90 jours, seule
        # la série quotidienne est conservée. Sans cette purge la table grossit
        # indéfiniment (une ligne par position et par actualisation).
        db.execute("DELETE FROM price_history WHERE ts < datetime('now','-90 days')")
