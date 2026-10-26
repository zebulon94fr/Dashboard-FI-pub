"""Rapport mensuel : ce que le mois a fait au patrimoine, et pourquoi.

Le résumé hebdomadaire envoyé sur Telegram donne une photographie : combien
vous avez, combien vous avez gagné depuis le début. Il ne dit rien du mois
écoulé, et surtout rien de la seule question qui vaille à cette échéance :
sur ce que le patrimoine a bougé ce mois-ci, **quelle part vient du marché et
quelle part de votre épargne ?**

Un mois à +4 000 € dont 3 500 € de versements n'est pas un bon mois de marché,
c'est un bon mois d'épargne. Les deux méritent d'être connus, et ils ne se
pilotent pas pareil. Le rapport les sépare par une identité vérifiable :

    variation du patrimoine = flux nets + gain de marché

où le gain de marché est ce qui reste une fois les versements et les retraits
retirés — exactement la correction qu'applique le TWR, appliquée ici au mois.

Le mois par défaut est le **mois précédent** : le rapport part le 1er, et un
rapport du mois en cours n'aurait qu'une journée à raconter.
"""
import calendar
import datetime

from backend.analyse import repartition_classes
from backend.db import get_db
from backend.performance import flux_par_date
from catalog import ORDRE_TRANSACTIONS, TYPES_PASSIF, TYPES_TRANSACTION

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
           "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

# En deçà, un écart d'allocation ne mérite pas d'être signalé dans un rapport
# mensuel : c'est du bruit de marché, pas une dérive. L'onglet Rebalancing,
# lui, applique la règle 5/25 et propose des ordres — c'est son travail.
ECART_SIGNALE_PTS = 2.0


class RapportError(ValueError):
    """Erreur de saisie renvoyée telle quelle au client (HTTP 400)."""


def mois_precedent(aujourdhui=None):
    """« YYYY-MM » du mois précédent : celui que le rapport du 1er raconte."""
    jour = aujourdhui or datetime.date.today()
    premier = jour.replace(day=1)
    veille = premier - datetime.timedelta(days=1)
    return f"{veille.year:04d}-{veille.month:02d}"


def bornes(mois):
    """Premier et dernier jour du mois « YYYY-MM », en ISO."""
    try:
        annee, numero = (int(p) for p in str(mois).split("-")[:2])
        debut = datetime.date(annee, numero, 1)
    except (ValueError, TypeError):
        raise RapportError(
            f"Mois illisible : « {mois} ». Attendu au format AAAA-MM, par exemple 2026-09."
        )
    fin = datetime.date(annee, numero, calendar.monthrange(annee, numero)[1])
    return debut.isoformat(), fin.isoformat()


def libelle(mois):
    """« octobre 2026 », pour un titre."""
    annee, numero = (int(p) for p in str(mois).split("-")[:2])
    return f"{MOIS_FR[numero - 1]} {annee}"


# ══════════════════════════════════════════════════════════════
# VALORISATION ET PERFORMANCE DU MOIS
# ══════════════════════════════════════════════════════════════
def _serie(db, account_id, debut, fin):
    """Valorisations connues du compte sur le mois : [(date, valorisation)]."""
    return [(r["date"], r["valorisation"]) for r in db.execute("""
        SELECT date, valorisation FROM history_daily
        WHERE account_id = ? AND date >= ? AND date <= ? ORDER BY date ASC
    """, (account_id, debut, fin)).fetchall()]


def _valeur_avant(db, account_id, debut):
    """
    Dernière valorisation connue **avant** le mois : le point de départ.

    Prendre le premier jour du mois comme départ perdrait la performance du
    1er, et ferait démarrer le rapport d'un patrimoine qui a déjà bougé.
    """
    ligne = db.execute("""
        SELECT date, valorisation FROM history_daily
        WHERE account_id = ? AND date < ? ORDER BY date DESC LIMIT 1
    """, (account_id, debut)).fetchone()
    return (ligne["date"], ligne["valorisation"]) if ligne else None


def _performance(serie, depart, flux):
    """
    Performance du mois corrigée des flux, et sa décomposition.

    Même chaînage que le TWR : chaque journée vaut (V - flux) / V_veille - 1.
    Le gain de marché est la différence entre la variation constatée et les
    flux nets — c'est ce qui rend l'identité du préambule vérifiable.
    """
    if not serie:
        return None
    if depart is None:
        # Premier mois de l'historique : faute d'une valorisation antérieure,
        # le départ est la première journée connue du mois, et elle sort de la
        # série chaînée — sinon le mois partirait de zéro et afficherait une
        # performance infinie.
        if len(serie) < 2:
            return None
        depart, serie = serie[0], serie[1:]

    valeur_debut = depart[1]
    valeur_fin = serie[-1][1]
    flux_net = sum(flux.get(date, 0.0) for date, _ in serie)

    compose, precedent = 1.0, valeur_debut
    for date, valeur in serie:
        if precedent > 0:
            rendement = (valeur - flux.get(date, 0.0)) / precedent - 1
            if rendement > -1:
                compose *= (1 + rendement)
        precedent = valeur

    return {
        "date_depart": depart[0],
        "date_fin": serie[-1][0],
        "valeur_debut": round(valeur_debut, 2),
        "valeur_fin": round(valeur_fin, 2),
        "variation": round(valeur_fin - valeur_debut, 2),
        "flux_net": round(flux_net, 2),
        "gain_marche": round(valeur_fin - valeur_debut - flux_net, 2),
        "performance": round(compose - 1, 6) if valeur_debut > 0 else None,
        "nb_journees": len(serie),
        # La courbe du mois, départ compris : c'est le patrimoine tel qu'il a
        # été, versements inclus. La décomposition ci-dessus dit ce qui, dans
        # cette courbe, vient du marché.
        "serie": [{"date": date, "valorisation": round(valeur, 2)}
                  for date, valeur in [depart] + serie],
        "jours_flux": sorted({date for date, _ in serie if flux.get(date)}),
    }


# ══════════════════════════════════════════════════════════════
# MOUVEMENTS DU MOIS
# ══════════════════════════════════════════════════════════════
def _mouvements(db, debut, fin):
    """Mouvements du mois, par type et en détail."""
    lignes = db.execute("""
        SELECT t.id, t.date, t.type, t.nom, t.quantite, t.prix, t.devise,
               t.frais, t.montant_eur, t.note, a.nom compte, a.type compte_type
        FROM transactions t JOIN accounts a ON a.id = t.account_id
        WHERE t.date >= ? AND t.date <= ?
        ORDER BY t.date ASC, t.id ASC
    """, (debut, fin)).fetchall()

    par_type = {}
    for ligne in lignes:
        entree = par_type.setdefault(ligne["type"], {"nb": 0, "montant": 0.0})
        entree["nb"] += 1
        entree["montant"] += ligne["montant_eur"] or 0

    resume = [{
        "type": type_id,
        "label": TYPES_TRANSACTION[type_id]["label"],
        "icone": TYPES_TRANSACTION[type_id]["icone"],
        "nb": par_type[type_id]["nb"],
        "montant": round(par_type[type_id]["montant"], 2),
    } for type_id in ORDRE_TRANSACTIONS if type_id in par_type]

    return resume, [dict(ligne) for ligne in lignes]


def _dividendes(db, debut, fin):
    """Dividendes encaissés dans le mois, et cumul depuis le 1er janvier."""
    mois = db.execute("""
        SELECT d.date, d.nom, d.montant, d.montant_net, a.nom compte
        FROM dividendes d JOIN accounts a ON a.id = d.account_id
        WHERE d.date >= ? AND d.date <= ? ORDER BY d.date ASC
    """, (debut, fin)).fetchall()

    annee = db.execute(
        "SELECT COALESCE(SUM(montant), 0) total FROM dividendes WHERE date >= ? AND date <= ?",
        (debut[:4] + "-01-01", fin),
    ).fetchone()["total"]

    return {
        "lignes": [dict(d) for d in mois],
        "total": round(sum(d["montant"] or 0 for d in mois), 2),
        "cumul_annee": round(annee, 2),
    }


# ══════════════════════════════════════════════════════════════
# PAR COMPTE ET PAR CLASSE
# ══════════════════════════════════════════════════════════════
def _par_compte(db, debut, fin):
    """Variation du mois pour chaque compte, flux compris."""
    comptes = db.execute(
        "SELECT id, nom, type FROM accounts ORDER BY ordre, id"
    ).fetchall()

    sortie = []
    for compte in comptes:
        serie = _serie(db, compte["id"], debut, fin)
        depart = _valeur_avant(db, compte["id"], debut)
        if not serie:
            continue
        valeur_debut = depart[1] if depart else serie[0][1]
        valeur_fin = serie[-1][1]
        flux = flux_par_date(compte["id"], debut)
        flux_net = sum(montant for date, montant in flux.items() if debut <= date <= fin)
        sortie.append({
            "nom": compte["nom"], "type": compte["type"],
            "passif": compte["type"] in TYPES_PASSIF,
            "valeur_debut": round(valeur_debut, 2),
            "valeur_fin": round(valeur_fin, 2),
            "variation": round(valeur_fin - valeur_debut, 2),
            "flux_net": round(flux_net, 2),
            "gain_marche": round(valeur_fin - valeur_debut - flux_net, 2),
        })
    return sorted(sortie, key=lambda c: c["valeur_fin"], reverse=True)


def _allocation():
    """
    Écarts à l'allocation cible, au jour du rapport.

    Mesurés aujourd'hui et non à la fin du mois : une répartition par classe se
    reconstitue depuis les positions courantes, qui n'ont pas de mémoire. Le
    rapport le dit plutôt que de laisser croire à une photo d'époque.
    """
    repartition = repartition_classes()
    ecarts = []
    for classe in repartition["classes"]:
        if not classe["cible_pct"]:
            continue
        ecart = classe["poids"] * 100 - classe["cible_pct"]
        ecarts.append({
            "classe": classe["classe"], "label": classe["label"],
            "couleur": classe["couleur"],
            "poids_pct": round(classe["poids"] * 100, 2),
            "cible_pct": classe["cible_pct"],
            "ecart_pts": round(ecart, 2),
            "signale": abs(ecart) >= ECART_SIGNALE_PTS,
        })
    return {
        "total": repartition["total"],
        "classes": ecarts,
        "nb_signales": sum(1 for e in ecarts if e["signale"]),
        "cibles_definies": bool(ecarts),
    }


# ══════════════════════════════════════════════════════════════
# ASSEMBLAGE
# ══════════════════════════════════════════════════════════════
def rapport_mensuel(mois=None):
    """
    Rapport complet d'un mois. `mois` au format « AAAA-MM », défaut : le
    mois précédent.

    Retourne toujours un dictionnaire de même forme : sans historique sur le
    mois, `patrimoine` vaut None et `message` dit ce qui manque, plutôt que de
    renvoyer une erreur que l'appelant aurait à interpréter.
    """
    mois = mois or mois_precedent()
    debut, fin = bornes(mois)

    with get_db() as db:
        serie = _serie(db, 0, debut, fin)
        depart = _valeur_avant(db, 0, debut)
        flux = flux_par_date(None, debut)
        patrimoine = _performance(serie, depart, flux)
        resume, detail = _mouvements(db, debut, fin)
        dividendes = _dividendes(db, debut, fin)
        comptes = _par_compte(db, debut, fin)

    message = None
    if not serie:
        message = (f"Aucune valorisation enregistrée en {libelle(mois)} : le dashboard ne "
                   "tournait pas encore, ou les cours n'ont pas été actualisés ce mois-là.")
    elif depart is None:
        message = (f"Pas de valorisation connue avant le {debut} : le mois est le premier de "
                   "l'historique, sa variation se compte donc depuis sa première journée.")

    return {
        "mois": mois,
        "libelle": libelle(mois),
        "debut": debut,
        "fin": fin,
        "genere_le": datetime.date.today().isoformat(),
        "patrimoine": patrimoine,
        "mouvements": resume,
        "mouvements_detail": detail,
        "dividendes": dividendes,
        "comptes": comptes,
        "allocation": _allocation(),
        "message": message,
    }
