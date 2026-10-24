"""Versements programmés : un mouvement récurrent déclaré une fois.

Un journal ne vaut que s'il reste à jour, et le tenir à la main finit toujours
par être abandonné. Un virement mensuel vers un PEA est pourtant connu
d'avance : il suffit de le déclarer, et chaque échéance s'inscrit toute seule.

L'exécution est idempotente et rattrapante : elle inscrit toutes les échéances
dues depuis la dernière inscrite, si bien qu'un serveur arrêté deux semaines ne
perd rien, et que la relancer deux fois le même jour ne double rien.
"""
import datetime
import logging

from backend.db import get_db
from backend.positions import nombre
from backend.transactions import TransactionError, add_transaction
from catalog import TYPES_TRANSACTION

log = logging.getLogger("dashboard")

# Les mouvements sur une ligne précise (achat, vente) ne se programment pas :
# ils supposent un prix et une quantité qu'on ne connaît pas à l'avance.
TYPES_PROGRAMMABLES = [t for t, info in TYPES_TRANSACTION.items() if not info["ligne"]]

FREQUENCES = {
    "mensuel":     {"label": "Mensuel", "mois": 1},
    "trimestriel": {"label": "Trimestriel", "mois": 3},
    "annuel":      {"label": "Annuel", "mois": 12},
}

JOUR_MAX = 28


# ══════════════════════════════════════════════════════════════
# ÉCHÉANCIER
# ══════════════════════════════════════════════════════════════
def _mois_decale(annee, mois, pas):
    """(année, mois) décalés de `pas` mois, en restant sur un mois valide."""
    total = annee * 12 + (mois - 1) + pas
    return total // 12, total % 12 + 1


def echeances(debut, jour, frequence, jusqu_a, apres=""):
    """
    Dates dues d'un programme, de `debut` à `jusqu_a` inclus.

    `apres` est la dernière échéance déjà inscrite : les dates antérieures ou
    égales sont ignorées, ce qui rend l'appel rejouable sans rien doubler.
    """
    pas = FREQUENCES[frequence]["mois"]
    annee, mois = debut.year, debut.month
    courante = datetime.date(annee, mois, jour)
    if courante < debut:
        annee, mois = _mois_decale(annee, mois, pas)
        courante = datetime.date(annee, mois, jour)

    dues = []
    while courante <= jusqu_a:
        iso = courante.isoformat()
        if iso > apres:
            dues.append(iso)
        annee, mois = _mois_decale(annee, mois, pas)
        courante = datetime.date(annee, mois, jour)
    return dues


# ══════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════
def _date(valeur, champ, obligatoire=True):
    texte = (valeur or "").strip()
    if not texte:
        if obligatoire:
            raise TransactionError(f"La date {champ} est obligatoire (format AAAA-MM-JJ).")
        return ""
    try:
        return datetime.date.fromisoformat(texte).isoformat()
    except ValueError:
        raise TransactionError(f"La date {champ} doit être au format AAAA-MM-JJ.")


def _valide(db, payload):
    try:
        account_id = int(payload.get("account_id"))
    except (TypeError, ValueError):
        raise TransactionError("Le compte est obligatoire.")
    if not db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
        raise TransactionError("Compte introuvable.")

    type_tx = (payload.get("type") or "versement").strip().lower()
    if type_tx not in TYPES_PROGRAMMABLES:
        raise TransactionError(
            f"Type de mouvement non programmable : « {type_tx} ». "
            f"Valeurs acceptées : {', '.join(TYPES_PROGRAMMABLES)}. "
            "Un achat ou une vente suppose un prix connu d'avance."
        )

    frequence = (payload.get("frequence") or "mensuel").strip().lower()
    if frequence not in FREQUENCES:
        raise TransactionError(
            f"Fréquence inconnue : « {frequence} ». "
            f"Valeurs acceptées : {', '.join(FREQUENCES)}."
        )

    montant = nombre(payload.get("montant_eur", payload.get("montant")))
    if montant <= 0:
        raise TransactionError("Le montant doit être supérieur à zéro.")

    try:
        jour = int(payload.get("jour") or 1)
    except (TypeError, ValueError):
        raise TransactionError("Le jour du mois doit être un nombre.")
    if not 1 <= jour <= JOUR_MAX:
        raise TransactionError(
            f"Le jour du mois doit être compris entre 1 et {JOUR_MAX} : "
            "au-delà, l'échéance n'existe pas tous les mois."
        )

    debut = _date(payload.get("debut"), "de début")
    fin = _date(payload.get("fin"), "de fin", obligatoire=False)
    if fin and fin < debut:
        raise TransactionError("La date de fin précède la date de début.")

    return {
        "account_id": account_id, "type": type_tx, "montant_eur": round(montant, 2),
        "frequence": frequence, "jour": jour, "debut": debut, "fin": fin,
        "actif": 1 if payload.get("actif", True) else 0,
        "note": (payload.get("note") or "").strip()[:200],
    }


# ══════════════════════════════════════════════════════════════
# EXÉCUTION
# ══════════════════════════════════════════════════════════════
def executer(jusqu_a=None):
    """
    Inscrit au journal toutes les échéances dues, et retourne ce qui a été fait.

    Les mouvements sont créés hors de toute transaction SQL ouverte :
    `add_transaction` prend sa propre connexion, et l'imbriquer bloquerait.
    """
    limite = jusqu_a or datetime.date.today()
    if isinstance(limite, str):
        limite = datetime.date.fromisoformat(limite)

    with get_db() as db:
        programmes = [dict(r) for r in db.execute(
            "SELECT * FROM versements_programmes WHERE actif = 1 ORDER BY id"
        )]

    cree, echecs = 0, []
    derniere_par_programme = {}
    for programme in programmes:
        fin = programme["fin"] or ""
        borne = min(limite, datetime.date.fromisoformat(fin)) if fin else limite
        dues = echeances(
            datetime.date.fromisoformat(programme["debut"]), programme["jour"],
            programme["frequence"], borne, programme["derniere_echeance"] or "",
        )
        for date in dues:
            try:
                add_transaction({
                    "date": date, "account_id": programme["account_id"],
                    "type": programme["type"], "montant": programme["montant_eur"],
                    "note": programme["note"] or "Versement programmé",
                })
                cree += 1
                derniere_par_programme[programme["id"]] = date
            except Exception as e:
                # Les échéances d'un programme sont solidaires : on s'arrête à
                # la première qui échoue pour que les suivantes restent dues,
                # sans empêcher les autres programmes de s'exécuter.
                log.warning(f"Versement programmé #{programme['id']} au {date} : {e}")
                echecs.append({"programme_id": programme["id"], "date": date, "erreur": str(e)})
                break

    if derniere_par_programme:
        with get_db() as db:
            for programme_id, date in derniere_par_programme.items():
                db.execute(
                    "UPDATE versements_programmes SET derniere_echeance=? WHERE id=?",
                    (date, programme_id),
                )

    return {"mouvements_crees": cree, "programmes_actifs": len(programmes), "echecs": echecs}


# ══════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════
def list_programmes():
    with get_db() as db:
        rows = db.execute("""
            SELECT v.*, a.nom compte, a.type compte_type
            FROM versements_programmes v LEFT JOIN accounts a ON a.id = v.account_id
            ORDER BY v.actif DESC, a.ordre, v.id
        """).fetchall()

    aujourdhui = datetime.date.today()
    programmes = []
    for row in rows:
        p = dict(row)
        p["frequence_label"] = FREQUENCES.get(p["frequence"], {}).get("label", p["frequence"])
        p["prochaine"] = _prochaine(p, aujourdhui)
        programmes.append(p)
    return programmes


def _prochaine(programme, aujourdhui):
    """Prochaine échéance à venir, ou None si le programme est éteint ou terminé."""
    if not programme["actif"]:
        return None
    # Assez loin pour couvrir une période entière, pas plus : on ne cherche
    # que la prochaine date, pas tout l'échéancier.
    horizon = aujourdhui + datetime.timedelta(
        days=400 + 31 * FREQUENCES[programme["frequence"]]["mois"])
    fin = programme["fin"] or ""
    if fin:
        horizon = min(horizon, datetime.date.fromisoformat(fin))
    futures = [d for d in echeances(
        datetime.date.fromisoformat(programme["debut"]), programme["jour"],
        programme["frequence"], horizon, programme["derniere_echeance"] or "",
    ) if d > aujourdhui.isoformat()]
    return futures[0] if futures else None


def add_programme(payload):
    with get_db() as db:
        champs = _valide(db, payload)
        cur = db.execute("""
            INSERT INTO versements_programmes
              (account_id, type, montant_eur, frequence, jour, debut, fin, actif, note)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (champs["account_id"], champs["type"], champs["montant_eur"], champs["frequence"],
              champs["jour"], champs["debut"], champs["fin"], champs["actif"], champs["note"]))
        return cur.lastrowid


def update_programme(programme_id, payload):
    with get_db() as db:
        if not db.execute("SELECT id FROM versements_programmes WHERE id=?",
                          (programme_id,)).fetchone():
            raise TransactionError("Versement programmé introuvable.")
        champs = _valide(db, payload)
        db.execute("""
            UPDATE versements_programmes SET
              account_id=?, type=?, montant_eur=?, frequence=?, jour=?, debut=?, fin=?,
              actif=?, note=?
            WHERE id=?
        """, (champs["account_id"], champs["type"], champs["montant_eur"], champs["frequence"],
              champs["jour"], champs["debut"], champs["fin"], champs["actif"], champs["note"],
              programme_id))


def delete_programme(programme_id):
    """Supprime le programme. Les mouvements déjà inscrits au journal restent."""
    with get_db() as db:
        if not db.execute("SELECT id FROM versements_programmes WHERE id=?",
                          (programme_id,)).fetchone():
            raise TransactionError("Versement programmé introuvable.")
        db.execute("DELETE FROM versements_programmes WHERE id=?", (programme_id,))
