"""Journal des mouvements : CRUD, prix moyen pondéré et plus-values réalisées.

Le journal est la source de vérité d'une position. Dès qu'un achat ou une vente
y est enregistré, la quantité, le PRU et le prix de revient en euros de la
position sont recalculés à partir de lui : une saisie manuelle sur ces trois
champs est réécrite au prochain recalcul.

Deux familles de mouvements, distinguées par `ligne` dans le catalogue :

  * `achat` et `vente` portent sur une position précise et déterminent son PMP ;
  * `versement`, `retrait` et `frais` portent sur l'enveloppe entière et ne
    servent qu'à dater les flux (TWR, TRI — voir performance.py).

Un compte peut tenir une **ligne d'espèces** (`positions.especes`). Le journal
y inscrit alors tout seul la contrepartie de chaque mouvement, en double
partie : acheter un titre vend des espèces, un versement en achète. Sans cela,
les liquidités restent hors du patrimoine valorisé, et convertir du cash en
titres fait bondir le patrimoine comme si l'argent venait de nulle part.

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
# CONTREPARTIE EN ESPÈCES
# ══════════════════════════════════════════════════════════════
# Le mouvement qu'écrit l'utilisateur, et celui que le journal inscrit en face.
# Le sens s'inverse : ce qui entre quelque part sort d'ailleurs.
CONTREPARTIE = {
    "achat": "vente", "vente": "achat",
    "versement": "achat", "retrait": "vente", "frais": "vente",
}

# Une paire ne vaut jamais que le flux voulu par son origine.
#
# Un achat réglé en espèces déjà détenues ne fait entrer aucun argent neuf :
# sa contrepartie compte donc comme un flux, et annule celui de l'achat. Un
# versement, lui, fait bien entrer de l'argent : sa contrepartie n'en est pas
# un, puisque le versement le porte déjà pour les deux.
CONTREPARTIE_EST_UN_FLUX = {"achat", "vente"}

NOTE_CONTREPARTIE = "Contrepartie en espèces, inscrite par le journal"


def ligne_especes(db, account_id, sauf=None):
    """La ligne qui porte les espèces du compte, s'il en tient une."""
    ligne = db.execute(
        "SELECT * FROM positions WHERE account_id=? AND especes=1 LIMIT 1", (account_id,)
    ).fetchone()
    return None if ligne is None or ligne["id"] == sauf else ligne


def _inscrire_contrepartie(db, champs, origine_id):
    """
    Inscrit en face du mouvement son mouvement d'espèces, s'il y a lieu.

    La quantité vaut le montant en euros et le prix unitaire 1 : une ligne
    d'espèces se compte en euros, son PRU reste à 1 et ne porte donc jamais de
    plus-value. Les frais sont déjà compris dans `montant_eur`, ce qui fait
    sortir des espèces ce que l'opération a réellement coûté.
    """
    especes = ligne_especes(db, champs["account_id"], sauf=champs["position_id"])
    if especes is None:
        return
    montant = round(champs["montant_eur"], 2)
    if montant <= 0:
        return

    type_contrepartie = CONTREPARTIE[champs["type"]]
    db.execute("""
        INSERT INTO transactions
          (date, account_id, position_id, type, nom, quantite, prix,
           devise, taux_change, frais, montant_eur, origine_id, flux, note)
        VALUES (?,?,?,?,?,?,?,'EUR',1.0,0,?,?,?,?)
    """, (
        champs["date"], champs["account_id"], especes["id"], type_contrepartie,
        especes["nom"], montant, 1.0, montant, origine_id,
        1 if champs["type"] in CONTREPARTIE_EST_UN_FLUX else 0,
        NOTE_CONTREPARTIE,
    ))
    recalc_position(especes["id"], db)


def _retirer_contrepartie(db, origine_id):
    """Supprime la contrepartie d'un mouvement, et recalcule la ligne d'espèces."""
    ligne = db.execute(
        "SELECT id, position_id FROM transactions WHERE origine_id=?", (origine_id,)
    ).fetchone()
    if ligne is None:
        return
    db.execute("DELETE FROM transactions WHERE id=?", (ligne["id"],))
    if ligne["position_id"]:
        recalc_position(ligne["position_id"], db)


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


def positions_sans_journal():
    """
    Positions dont le prix de revient en euros n'est qu'une estimation.

    Aucun achat ni vente ne les adosse au journal : leur `cout_eur` vaut NULL
    et se recalcule au taux du moment à chaque actualisation, ce qui fait
    disparaître des comptes le gain de change sur le capital.
    """
    with get_db() as db:
        rows = db.execute("""
            SELECT p.id, p.nom, p.quantite, p.pru, p.devise, p.valorisation,
                   p.account_id, a.nom compte, a.type compte_type
            FROM positions p LEFT JOIN accounts a ON a.id = p.account_id
            WHERE p.quantite > 0 AND p.pru > 0
              AND NOT EXISTS (SELECT 1 FROM transactions t
                              WHERE t.position_id = p.id AND t.type IN ('achat','vente'))
            ORDER BY a.ordre, p.valorisation DESC
        """).fetchall()
    return [dict(r) for r in rows]


def ouvrir_position(position_id, date, taux_change=None):
    """
    Inscrit au journal l'achat d'ouverture d'une position saisie à la main.

    Sans taux fourni, celui du jour de l'achat est récupéré au marché : c'est
    tout l'intérêt de l'opération. Figer le prix de revient au cours d'alors
    rend au portefeuille le gain — ou la perte — de change sur le capital, que
    l'estimation au taux du moment efface.
    """
    with get_db() as db:
        position = db.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        if not position:
            raise TransactionError("Position introuvable.")
        if position["quantite"] <= 0 or position["pru"] <= 0:
            raise TransactionError(
                f"« {position['nom']} » n'a ni quantité ni PRU : il n'y a pas d'achat à reconstituer."
            )
        deja = db.execute(
            "SELECT COUNT(*) n FROM transactions WHERE position_id=? AND type IN ('achat','vente')",
            (position_id,),
        ).fetchone()["n"]
        if deja:
            raise TransactionError(
                f"« {position['nom']} » a déjà {deja} mouvement{'s' if deja > 1 else ''} au journal : "
                "son prix de revient en découle déjà."
            )
        ouverture = {
            "date": date, "account_id": position["account_id"], "position_id": position_id,
            "type": "achat", "quantite": position["quantite"], "prix": position["pru"],
            "devise": position["devise"], "taux_change": taux_change,
            "note": "Achat d'ouverture, reconstitué depuis la saisie manuelle",
        }

    return add_transaction(ouverture)


def versements_cumules(db=None):
    """
    Total versé sur chaque enveloppe depuis l'ouverture, en euros.

    C'est la grandeur que surveillent les plafonds réglementaires — 150 000 €
    sur un PEA. Elle ne retranche pas les retraits : le plafond porte sur les
    versements bruts cumulés, et un retrait ne libère pas de place. Les achats
    n'y entrent pas non plus, puisqu'ils déplacent de l'argent déjà versé.
    """
    if db is None:
        with get_db() as connexion:
            return versements_cumules(connexion)

    return {
        row["account_id"]: round(row["total"], 2)
        for row in db.execute("""
            SELECT account_id, SUM(montant_eur) total FROM transactions
            WHERE type = 'versement' GROUP BY account_id
        """)
    }


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
        # Une ligne d'espèces s'achète et se vend à 1 € : sa plus-value est
        # nulle par construction, et la faire figurer parmi les lignes cédées
        # ferait croire à une opération imposable là où il n'y a qu'un virement.
        lignes = db.execute(f"""
            SELECT t.position_id, t.nom, t.account_id, a.nom compte, a.type compte_type
            FROM transactions t
            LEFT JOIN accounts a ON a.id = t.account_id
            LEFT JOIN positions p ON p.id = t.position_id
            {clause}{' AND' if clause else 'WHERE'} COALESCE(p.especes, 0) = 0
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

        # Capital engagé et retiré comptent ce qui **traverse la frontière**
        # de l'enveloppe, pas chaque écriture. Un achat réglé en espèces déjà
        # détenues n'apporte rien de neuf : lui comme sa contrepartie sortent
        # du compte. Sans cela, verser 700 € puis en investir 612 afficherait
        # 2 012 € de capital engagé pour 700 € réellement apportés.
        # Est externe le mouvement qui n'est pas une contrepartie, et dont la
        # contrepartie — s'il en a une — ne porte pas elle-même de flux. Un
        # versement a bien une contrepartie en espèces, mais elle est marquée
        # `flux = 0` : le versement reste donc un apport. Un achat réglé en
        # espèces, lui, a une contrepartie qui annule la sienne : les deux
        # sortent du compte.
        externe = ("t.origine_id IS NULL AND NOT EXISTS "
                   "(SELECT 1 FROM transactions c WHERE c.origine_id = t.id AND c.flux = 1)")
        stats = db.execute(f"""
            SELECT COUNT(*) nb,
                   ROUND(SUM(CASE WHEN type IN ('achat','versement') AND {externe}
                                  THEN montant_eur ELSE 0 END), 2) total_entrees,
                   ROUND(SUM(CASE WHEN type IN ('vente','retrait','frais') AND {externe}
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
        _inscrire_contrepartie(db, champs, cur.lastrowid)
        return cur.lastrowid


def update_transaction(transaction_id, payload):
    with get_db() as db:
        ancienne = db.execute(
            "SELECT position_id, origine_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not ancienne:
            raise TransactionError("Mouvement introuvable.")
        if ancienne["origine_id"]:
            raise TransactionError(
                "Ce mouvement est la contrepartie en espèces d'un autre : modifiez "
                "le mouvement d'origine, sa contrepartie suivra."
            )

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

        # Montant, date ou compte ont pu changer : on réécrit la contrepartie
        # plutôt que de la rapiécer champ par champ.
        _retirer_contrepartie(db, transaction_id)
        _inscrire_contrepartie(db, champs, transaction_id)


def delete_transaction(transaction_id):
    with get_db() as db:
        ligne = db.execute(
            "SELECT position_id, origine_id FROM transactions WHERE id=?", (transaction_id,)
        ).fetchone()
        if not ligne:
            raise TransactionError("Mouvement introuvable.")
        if ligne["origine_id"]:
            raise TransactionError(
                "Ce mouvement est la contrepartie en espèces d'un autre : supprimez "
                "le mouvement d'origine, sa contrepartie partira avec lui."
            )

        # La contrepartie part d'abord : son `origine_id` la ferait disparaître
        # en cascade, mais la ligne d'espèces resterait à recalculer.
        _retirer_contrepartie(db, transaction_id)
        db.execute("DELETE FROM transactions WHERE id=?", (transaction_id,))
        if ligne["position_id"]:
            recalc_position(ligne["position_id"], db)
