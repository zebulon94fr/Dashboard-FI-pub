"""Journal des mouvements : CRUD, prix moyen pondéré et plus-values réalisées.

Le journal est la source de vérité d'une position. Dès qu'un achat ou une vente
y est enregistré, la quantité, le PRU et le prix de revient en euros de la
position sont recalculés à partir de lui : une saisie manuelle sur ces trois
champs est réécrite au prochain recalcul.

Deux familles de mouvements, distinguées par `ligne` dans le catalogue :

  * `achat` et `vente` portent sur une position précise et déterminent son PMP ;
  * `versement`, `retrait` et `frais` portent sur l'enveloppe entière et ne
    servent qu'à dater les flux (TWR, TRI — voir performance.py).

Le prix moyen pondéré suit la règle française : un achat le fait bouger, une
vente ne le change pas et sort une quote-part du prix de revient.
"""
import datetime

from backend.db import get_db
from backend.positions import calculs, nombre, resoudre_taux
from catalog import ORDRE_TRANSACTIONS, TYPES_TRANSACTION


class TransactionError(ValueError):
    """Erreur de validation renvoyée telle quelle au client (HTTP 400)."""


# ══════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════
def _valide(db, payload):
    date = (payload.get("date") or "").strip()
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise TransactionError("La date du mouvement doit être au format AAAA-MM-JJ.")

    type_tx = (payload.get("type") or "").strip().lower()
    if type_tx not in TYPES_TRANSACTION:
        raise TransactionError(
            f"Type de mouvement inconnu : « {type_tx} ». "
            f"Valeurs acceptées : {', '.join(ORDRE_TRANSACTIONS)}."
        )

    try:
        account_id = int(payload.get("account_id"))
    except (TypeError, ValueError):
        raise TransactionError("Le compte est obligatoire.")
    if not db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
        raise TransactionError("Compte introuvable.")

    champs = {
        "date": date, "type": type_tx, "account_id": account_id,
        "note": (payload.get("note") or "").strip()[:200],
        "frais": max(0.0, nombre(payload.get("frais"))),
        "quantite": 0.0, "prix": 0.0, "devise": "EUR", "taux_change": 1.0,
        "position_id": None, "nom": "",
    }

    if TYPES_TRANSACTION[type_tx]["ligne"]:
        _valide_ligne(db, payload, champs, type_tx, account_id, date)
    else:
        montant = nombre(payload.get("montant"))
        if montant <= 0:
            raise TransactionError(
                f"Le montant d'un mouvement « {TYPES_TRANSACTION[type_tx]['label'].lower()} » "
                "doit être supérieur à zéro."
            )
        champs["montant_eur"] = round(montant, 2)
        # Pas de ligne concernée : `nom` ne sert qu'à un libellé libre.
        champs["nom"] = (payload.get("nom") or "").strip()[:120]

    return champs


def _valide_ligne(db, payload, champs, type_tx, account_id, date):
    """Champs propres à un achat ou à une vente, qui portent sur une position."""
    try:
        position_id = int(payload.get("position_id"))
    except (TypeError, ValueError):
        raise TransactionError("Un achat ou une vente doit désigner une position.")

    position = db.execute(
        "SELECT * FROM positions WHERE id=? AND account_id=?", (position_id, account_id)
    ).fetchone()
    if not position:
        raise TransactionError("Position introuvable dans ce compte.")

    quantite = nombre(payload.get("quantite"))
    prix = nombre(payload.get("prix"))
    if quantite <= 0:
        raise TransactionError("La quantité doit être supérieure à zéro.")
    if prix <= 0:
        raise TransactionError("Le prix unitaire doit être supérieur à zéro.")

    devise = ((payload.get("devise") or position["devise"] or "EUR").strip().upper() or "EUR")[:3]
    taux = resoudre_taux(db, devise, payload.get("taux_change"), date)

    brut = quantite * prix * taux
    champs.update({
        "position_id": position_id,
        "nom": position["nom"],
        "quantite": quantite,
        "prix": prix,
        "devise": devise,
        "taux_change": taux,
        # Les frais alourdissent un achat et allègent le produit d'une vente.
        "montant_eur": round(brut + champs["frais"] if type_tx == "achat"
                             else brut - champs["frais"], 2),
    })


# ══════════════════════════════════════════════════════════════
# PRIX MOYEN PONDÉRÉ
# ══════════════════════════════════════════════════════════════
def _parcours_ledger(mouvements):
    """
    Rejoue le journal d'une position et renvoie son état courant.

    Retourne (quantite, pru, cout_eur, pv_realisee, ventes) : le PRU est exprimé
    dans la devise de la position, le prix de revient et la plus-value réalisée
    en euros.
    """
    quantite = 0.0
    cout_devise = 0.0      # prix de revient dans la devise, pour le PRU
    cout_eur = 0.0         # prix de revient réellement supporté, en euros
    pv_realisee = 0.0
    ventes = 0

    for m in mouvements:
        if m["type"] == "achat":
            quantite += m["quantite"]
            cout_devise += m["quantite"] * m["prix"]
            cout_eur += m["montant_eur"]

        elif m["type"] == "vente":
            if quantite <= 0:
                continue                      # vente sans stock : rien à sortir
            vendue = min(m["quantite"], quantite)
            part = vendue / quantite
            # Une vente ne modifie pas le PRU : elle en sort une quote-part.
            pv_realisee += m["montant_eur"] - cout_eur * part
            cout_eur -= cout_eur * part
            cout_devise -= cout_devise * part
            quantite -= vendue
            ventes += 1

    if quantite <= 1e-12:                     # ligne soldée
        quantite, cout_devise, cout_eur = 0.0, 0.0, 0.0

    pru = (cout_devise / quantite) if quantite else 0.0
    return quantite, pru, cout_eur, pv_realisee, ventes


def recalc_position(position_id, db=None):
    """
    Réécrit quantité, PRU et prix de revient d'une position depuis son journal.

    Sans mouvement enregistré, la position garde sa saisie manuelle : le
    dashboard reste utilisable sans tenir de journal.
    """
    if db is None:
        with get_db() as connexion:
            return recalc_position(position_id, connexion)

    position = db.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
    if not position:
        return None

    mouvements = db.execute(
        "SELECT type, quantite, prix, montant_eur FROM transactions "
        "WHERE position_id=? AND type IN ('achat','vente') ORDER BY date ASC, id ASC",
        (position_id,),
    ).fetchall()
    if not mouvements:
        return None

    quantite, pru, cout_eur, _pv, _n = _parcours_ledger(mouvements)
    valo, pv, pct = calculs(quantite, pru, position["cours"], position["taux_change"], cout_eur)

    db.execute("""
        UPDATE positions SET
          quantite=?, pru=?, cout_eur=?, valorisation=?, pv_latent=?, pv_pct=?,
          updated_at=datetime('now')
        WHERE id=?
    """, (quantite, round(pru, 6), round(cout_eur, 2), valo, pv, pct, position_id))
    return quantite


def plus_values_realisees(account_id=None, annee=None):
    """
    Plus-values réalisées par position, reconstituées depuis le journal.

    C'est le montant imposable — celui que le dashboard ne savait pas voir tant
    qu'il ne connaissait que l'état courant des positions.
    """
    where, params = [], []
    if account_id:
        where.append("t.account_id=?")
        params.append(int(account_id))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with get_db() as db:
        lignes = db.execute(f"""
            SELECT t.position_id, t.nom, t.account_id, a.nom compte, a.type compte_type
            FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
            {clause}
            GROUP BY t.position_id, t.nom, t.account_id
        """, params).fetchall()

        resultats = []
        for ligne in lignes:
            mouvements = db.execute("""
                SELECT type, date, quantite, prix, montant_eur FROM transactions
                WHERE type IN ('achat','vente') AND account_id=?
                  AND (position_id IS ? OR (position_id IS NULL AND nom=?))
                ORDER BY date ASC, id ASC
            """, (ligne["account_id"], ligne["position_id"], ligne["nom"])).fetchall()

            if annee:
                # On rejoue tout le journal — le prix de revient d'une vente
                # dépend des achats antérieurs — puis on ne retient que l'année.
                mouvements = [m for m in mouvements
                              if m["type"] == "achat" or m["date"][:4] == str(annee)]

            _q, _pru, _cout, pv, ventes = _parcours_ledger(mouvements)
            if ventes:
                resultats.append({
                    "nom": ligne["nom"], "compte": ligne["compte"],
                    "compte_type": ligne["compte_type"], "account_id": ligne["account_id"],
                    "pv_realisee": round(pv, 2), "nb_ventes": ventes,
                })

    resultats.sort(key=lambda r: r["pv_realisee"], reverse=True)
    return resultats


# ══════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════
def get_transactions(filters=None):
    filters = filters or {}
    where, params = [], []
    for colonne, cle in (("t.account_id", "account_id"), ("t.position_id", "position_id"),
                         ("t.type", "type")):
        if filters.get(cle):
            where.append(f"{colonne}=?")
            params.append(filters[cle] if cle == "type" else int(filters[cle]))
    if filters.get("annee"):
        where.append("strftime('%Y', t.date)=?")
        params.append(str(filters["annee"]))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with get_db() as db:
        rows = db.execute(f"""
            SELECT t.*, a.nom compte, a.type compte_type
            FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
            {clause} ORDER BY t.date DESC, t.id DESC
        """, params).fetchall()

        stats = db.execute(f"""
            SELECT COUNT(*) nb,
                   ROUND(SUM(CASE WHEN type IN ('achat','versement')
                                  THEN montant_eur ELSE 0 END), 2) total_entrees,
                   ROUND(SUM(CASE WHEN type IN ('vente','retrait','frais')
                                  THEN montant_eur ELSE 0 END), 2) total_sorties,
                   MIN(date) premier, MAX(date) dernier
            FROM transactions t {clause}
        """, params).fetchone()

    return {
        "transactions": [dict(r) for r in rows],
        "stats": dict(stats) if stats else {},
        "plus_values": plus_values_realisees(filters.get("account_id")),
    }


def add_transaction(payload):
    with get_db() as db:
        champs = _valide(db, payload)
        cur = db.execute("""
            INSERT INTO transactions
              (date, account_id, position_id, type, nom, quantite, prix,
               devise, taux_change, frais, montant_eur, note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            champs["date"], champs["account_id"], champs["position_id"], champs["type"],
            champs["nom"], champs["quantite"], champs["prix"], champs["devise"],
            champs["taux_change"], champs["frais"], champs["montant_eur"], champs["note"],
        ))
        if champs["position_id"]:
            recalc_position(champs["position_id"], db)
        return cur.lastrowid


def update_transaction(transaction_id, payload):
    with get_db() as db:
        ancienne = db.execute(
            "SELECT position_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not ancienne:
            raise TransactionError("Mouvement introuvable.")

        champs = _valide(db, payload)
        db.execute("""
            UPDATE transactions SET
              date=?, account_id=?, position_id=?, type=?, nom=?, quantite=?, prix=?,
              devise=?, taux_change=?, frais=?, montant_eur=?, note=?
            WHERE id=?
        """, (
            champs["date"], champs["account_id"], champs["position_id"], champs["type"],
            champs["nom"], champs["quantite"], champs["prix"], champs["devise"],
            champs["taux_change"], champs["frais"], champs["montant_eur"], champs["note"],
            transaction_id,
        ))
        # Les deux positions sont à recalculer si le mouvement a changé de ligne.
        for position_id in {ancienne["position_id"], champs["position_id"]} - {None}:
            recalc_position(position_id, db)


def delete_transaction(transaction_id):
    with get_db() as db:
        ligne = db.execute(
            "SELECT position_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not ligne:
            raise TransactionError("Mouvement introuvable.")
        db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
        if ligne["position_id"]:
            recalc_position(ligne["position_id"], db)
