"""CRUD des comptes (enveloppes) créés par l'utilisateur."""
import datetime

from catalog import ACCOUNT_TYPES, ORDRE_TYPES
from backend.db import get_db

CHAMPS = ("nom", "type", "etablissement", "date_ouverture", "cible_pct", "note", "ordre")


class AccountError(ValueError):
    """Erreur de validation renvoyée telle quelle au client (HTTP 400)."""


def _valide(payload, partiel=False):
    """Normalise et contrôle les champs d'un compte."""
    out = {}

    if not partiel or "nom" in payload:
        nom = (payload.get("nom") or "").strip()
        if not nom:
            raise AccountError("Le nom du compte est obligatoire.")
        if len(nom) > 80:
            raise AccountError("Le nom du compte est limité à 80 caractères.")
        out["nom"] = nom

    if not partiel or "type" in payload:
        type_id = (payload.get("type") or "").strip()
        if type_id not in ACCOUNT_TYPES:
            attendus = ", ".join(ORDRE_TYPES)
            raise AccountError(f"Type de compte inconnu : « {type_id} ». Valeurs acceptées : {attendus}.")
        out["type"] = type_id

    if "etablissement" in payload:
        out["etablissement"] = (payload.get("etablissement") or "").strip()[:80]

    if "note" in payload:
        out["note"] = (payload.get("note") or "").strip()[:500]

    if "date_ouverture" in payload:
        date = (payload.get("date_ouverture") or "").strip()
        if date:
            try:
                datetime.date.fromisoformat(date)
            except ValueError:
                raise AccountError("La date d'ouverture doit être au format AAAA-MM-JJ.")
        out["date_ouverture"] = date

    if "cible_pct" in payload:
        try:
            cible = float(payload.get("cible_pct") or 0)
        except (TypeError, ValueError):
            raise AccountError("L'allocation cible doit être un nombre.")
        out["cible_pct"] = min(100.0, max(0.0, cible))

    if "ordre" in payload:
        try:
            out["ordre"] = int(payload.get("ordre") or 0)
        except (TypeError, ValueError):
            out["ordre"] = 0

    return out


def list_accounts():
    """Comptes avec leurs agrégats (valorisation, investi, +/- latent)."""
    with get_db() as db:
        rows = db.execute("""
            SELECT a.*,
                   COUNT(p.id)                                       nb_positions,
                   COALESCE(SUM(p.valorisation), 0)                  valorisation,
                   COALESCE(SUM(p.pru * p.quantite * p.taux_change), 0) investi,
                   COALESCE(SUM(p.pv_latent), 0)                     pv_latent
            FROM accounts a
            LEFT JOIN positions p ON p.account_id = a.id
            GROUP BY a.id
            ORDER BY a.ordre, a.id
        """).fetchall()

    comptes = []
    for row in rows:
        c = dict(row)
        c["pv_pct"] = (c["pv_latent"] / c["investi"]) if c["investi"] else 0
        c["type_label"] = ACCOUNT_TYPES.get(c["type"], {}).get("label", c["type"])
        comptes.append(c)
    return comptes


def get_account(account_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return dict(row) if row else None


def create_account(payload):
    champs = _valide(payload)
    with get_db() as db:
        if champs.get("ordre") is None or "ordre" not in champs:
            prochain = db.execute("SELECT COALESCE(MAX(ordre), 0) + 1 n FROM accounts").fetchone()["n"]
            champs["ordre"] = prochain
        cols = [c for c in CHAMPS if c in champs]
        placeholders = ",".join("?" for _ in cols)
        cur = db.execute(
            f"INSERT INTO accounts ({','.join(cols)}) VALUES ({placeholders})",
            [champs[c] for c in cols],
        )
        return cur.lastrowid


def update_account(account_id, payload):
    champs = _valide(payload, partiel=True)
    if not champs:
        return
    cols = [c for c in CHAMPS if c in champs]
    assignations = ",".join(f"{c}=?" for c in cols)
    with get_db() as db:
        cur = db.execute(
            f"UPDATE accounts SET {assignations} WHERE id=?",
            [champs[c] for c in cols] + [account_id],
        )
        if cur.rowcount == 0:
            raise AccountError("Compte introuvable.")


def delete_account(account_id):
    """Supprime le compte, ses positions et ses dividendes (ON DELETE CASCADE)."""
    with get_db() as db:
        cur = db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        if cur.rowcount == 0:
            raise AccountError("Compte introuvable.")
        db.execute("DELETE FROM history_daily WHERE account_id=?", (account_id,))
        db.execute("DELETE FROM history_intraday WHERE account_id=?", (account_id,))


def save_cibles(cibles):
    """Enregistre les allocations cibles : {account_id: pourcentage}."""
    with get_db() as db:
        for account_id, pct in (cibles or {}).items():
            try:
                valeur = min(100.0, max(0.0, float(pct)))
            except (TypeError, ValueError):
                continue
            db.execute("UPDATE accounts SET cible_pct=? WHERE id=?", (valeur, int(account_id)))


def anciennete_ans(date_ouverture, aujourdhui=None):
    """Ancienneté du compte en années décimales, ou None si la date est absente."""
    if not date_ouverture:
        return None
    try:
        ouverture = datetime.date.fromisoformat(date_ouverture)
    except ValueError:
        return None
    aujourdhui = aujourdhui or datetime.date.today()
    return round((aujourdhui - ouverture).days / 365.25, 2)
