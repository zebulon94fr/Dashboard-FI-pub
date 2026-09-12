"""Indépendance financière : patrimoine net, frais réels et capital-cible.

Le projet s'appelle Dashboard FI et ne mesurait rien de tout cela. Il répondait
à « combien j'aurai dans vingt ans », jamais à « dans combien de temps puis-je
arrêter » — qui est pourtant la question que pose quiconque installe un outil
portant ce nom.

Trois apports, dans l'ordre où ils se conditionnent :

  * le **patrimoine net**. Un patrimoine sans les liquidités, l'immobilier et
    les crédits n'est pas un patrimoine : pour un ménage français, la résidence
    principale et l'emprunt qui la finance sont souvent l'essentiel du bilan ;
  * les **frais réels**, moyenne pondérée des frais d'enveloppe et des frais de
    support. Ils ne se voient jamais sur un relevé et rognent pourtant le
    capital terminal d'environ un cinquième sur vingt-cinq ans ;
  * les **métriques FI**, qui découlent d'une seule saisie : les dépenses
    annuelles visées et l'épargne mensuelle.

Le capital qui finance l'indépendance est le capital *financier* : ni la
résidence principale, qui ne produit pas de revenu tant qu'on l'habite, ni les
crédits, déjà déduits. C'est explicite à l'écran, car le choix est discutable.
"""
import datetime

from backend.db import get_db
from catalog import ACCOUNT_TYPES, TYPES_PASSIF

# Taux de retrait par défaut. Les 4 % viennent d'études américaines à horizon
# trente ans, hors fiscalité française : c'est un ordre de grandeur, pas une loi.
TAUX_RETRAIT_DEFAUT = 0.04

# Types d'enveloppe exclus du capital qui finance l'indépendance.
TYPES_HORS_CAPITAL_FI = TYPES_PASSIF | {"immobilier"}

REGLAGES_DEFAUT = {
    "depenses_annuelles": 0.0,
    "epargne_mensuelle": 0.0,
    "taux_retrait": TAUX_RETRAIT_DEFAUT * 100,   # en %, comme à l'écran
    "rendement_reel": 4.0,                       # net d'inflation, en %
    "horizon_ans": 25,
}


# ══════════════════════════════════════════════════════════════
# RÉGLAGES
# ══════════════════════════════════════════════════════════════
def get_reglages():
    """Profil saisi par l'utilisateur, complété par les valeurs par défaut."""
    with get_db() as db:
        stockes = {r["cle"]: r["valeur"] for r in db.execute("SELECT cle, valeur FROM reglages")}

    reglages = dict(REGLAGES_DEFAUT)
    for cle, defaut in REGLAGES_DEFAUT.items():
        if cle in stockes:
            try:
                reglages[cle] = type(defaut)(float(stockes[cle]))
            except (TypeError, ValueError):
                pass
    reglages["renseigne"] = reglages["depenses_annuelles"] > 0
    return reglages


def save_reglages(payload):
    """Enregistre les réglages connus ; ignore en silence les clés inattendues."""
    with get_db() as db:
        for cle in REGLAGES_DEFAUT:
            if cle not in (payload or {}):
                continue
            try:
                valeur = float(payload[cle] or 0)
            except (TypeError, ValueError):
                continue
            db.execute("""
                INSERT INTO reglages (cle, valeur) VALUES (?,?)
                ON CONFLICT(cle) DO UPDATE SET valeur=excluded.valeur
            """, (cle, str(max(0.0, valeur))))
    return get_reglages()


# ══════════════════════════════════════════════════════════════
# PATRIMOINE NET
# ══════════════════════════════════════════════════════════════
def patrimoine():
    """
    Actif brut, passif et patrimoine net, avec le détail par enveloppe.

    Un compte de type passif — un crédit — porte son capital restant dû comme
    valorisation positive ; c'est ici qu'on lui applique son signe.
    """
    with get_db() as db:
        rows = db.execute("""
            SELECT a.id, a.nom, a.type, a.frais_pct,
                   COALESCE(SUM(p.valorisation), 0) valorisation,
                   COUNT(p.id) nb_positions
            FROM accounts a LEFT JOIN positions p ON p.account_id = a.id
            GROUP BY a.id ORDER BY a.ordre, a.id
        """).fetchall()

    actif_brut = passif = capital_fi = 0.0
    detail = []
    for r in rows:
        est_passif = r["type"] in TYPES_PASSIF
        valeur = r["valorisation"] or 0
        if est_passif:
            passif += valeur
        else:
            actif_brut += valeur
            if r["type"] not in TYPES_HORS_CAPITAL_FI:
                capital_fi += valeur

        detail.append({
            "id": r["id"], "nom": r["nom"], "type": r["type"],
            "label": ACCOUNT_TYPES.get(r["type"], {}).get("label", r["type"]),
            "couleur": ACCOUNT_TYPES.get(r["type"], {}).get("couleur", "#8b949e"),
            "valorisation": round(valeur, 2),
            "passif": est_passif,
            "compte_fi": not est_passif and r["type"] not in TYPES_HORS_CAPITAL_FI,
            "nb_positions": r["nb_positions"],
        })

    return {
        "actif_brut": round(actif_brut, 2),
        "passif": round(passif, 2),
        "patrimoine_net": round(actif_brut - passif, 2),
        "capital_fi": round(capital_fi, 2),
        "comptes": detail,
        "a_passif": passif > 0,
    }


# ══════════════════════════════════════════════════════════════
# FRAIS
# ══════════════════════════════════════════════════════════════
def frais():
    """
    Coût annuel des frais, en euros et en pourcentage pondéré.

    Deux étages se cumulent : les frais de gestion de l'enveloppe (assurance
    vie, PER) et les frais courants du support (TER d'un fonds). Ni l'un ni
    l'autre n'apparaît sur un relevé ; ensemble, ils décident pourtant d'une
    part considérable du capital terminal.

    Le périmètre est celui de l'épargne financière — le même que `capital_fi`.
    Y inclure une résidence principale, qui ne porte ni frais de gestion ni
    TER, diluerait le taux moyen et ferait disparaître la ponction réelle du
    rendement projeté.
    """
    exclus = tuple(TYPES_HORS_CAPITAL_FI)
    with get_db() as db:
        rows = db.execute(
            "SELECT a.nom compte, a.type, a.frais_pct, p.nom, p.ter, p.valorisation "
            "FROM positions p JOIN accounts a ON a.id = p.account_id "
            "WHERE p.valorisation > 0 AND a.type NOT IN (%s)"
            % ",".join("?" * len(exclus)), exclus).fetchall()

    total = sum(r["valorisation"] for r in rows)
    if not total:
        return {"total_valorise": 0, "cout_annuel": 0, "taux_moyen": 0,
                "lignes": [], "renseigne": False}

    cout = 0.0
    lignes = []
    for r in rows:
        taux = ((r["frais_pct"] or 0) + (r["ter"] or 0)) / 100
        montant = r["valorisation"] * taux
        cout += montant
        if taux > 0:
            lignes.append({
                "nom": r["nom"], "compte": r["compte"],
                "valorisation": round(r["valorisation"], 2),
                "frais_enveloppe": r["frais_pct"] or 0,
                "ter": r["ter"] or 0,
                "taux_total": round(taux, 6),
                "cout_annuel": round(montant, 2),
            })

    lignes.sort(key=lambda l: l["cout_annuel"], reverse=True)
    taux_moyen = cout / total

    return {
        "total_valorise": round(total, 2),
        "cout_annuel": round(cout, 2),
        "cout_mensuel": round(cout / 12, 2),
        "taux_moyen": round(taux_moyen, 6),
        "lignes": lignes,
        "renseigne": bool(lignes),
        # Ce que ces frais coûtent sur un horizon long, à rendement égal.
        "erosion_25_ans": round(1 - (1 - taux_moyen) ** 25, 6) if taux_moyen else 0,
    }


# ══════════════════════════════════════════════════════════════
# MÉTRIQUES D'INDÉPENDANCE
# ══════════════════════════════════════════════════════════════
def _annees_pour_atteindre(capital, cible, versement_annuel, rendement):
    """
    Nombre d'années avant d'atteindre `cible`, ou None si l'objectif fuit.

    Résolution analytique de capital x (1+r)^n + versement x annuité = cible,
    par recherche dichotomique sur n — plus court qu'une formule fermée et
    valable même à rendement nul.
    """
    if capital >= cible:
        return 0.0
    if versement_annuel <= 0 and rendement <= 0:
        return None

    def valeur_dans(n):
        if rendement <= 0:
            return capital + versement_annuel * n
        facteur = (1 + rendement) ** n
        return capital * facteur + versement_annuel * (facteur - 1) / rendement

    if valeur_dans(100) < cible:
        return None

    bas, haut = 0.0, 100.0
    for _ in range(200):
        milieu = (bas + haut) / 2
        if valeur_dans(milieu) < cible:
            bas = milieu
        else:
            haut = milieu
    return round(haut, 2)


def metriques(reglages=None):
    """Capital-cible, taux de couverture, date d'indépendance et Coast FI."""
    reglages = reglages or get_reglages()
    bilan = patrimoine()
    couts = frais()

    depenses = reglages["depenses_annuelles"]
    epargne_annuelle = reglages["epargne_mensuelle"] * 12
    taux_retrait = (reglages["taux_retrait"] or 0) / 100
    # Le rendement retenu est net d'inflation, et net des frais mesurés : c'est
    # celui qui fait réellement grossir le capital.
    rendement = (reglages["rendement_reel"] or 0) / 100 - (couts["taux_moyen"] or 0)
    capital = bilan["capital_fi"]

    if not reglages["renseigne"] or taux_retrait <= 0:
        return {
            "reglages": reglages, "patrimoine": bilan, "frais": couts,
            "capital_cible": None, "couverture": None, "message":
                "Renseignez vos dépenses annuelles pour que le dashboard puisse "
                "calculer un capital-cible, un taux de couverture et une date "
                "d'indépendance. C'est la seule donnée qu'il ne peut pas déduire des cours.",
        }

    capital_cible = depenses / taux_retrait
    couverture = capital / capital_cible if capital_cible else 0
    revenu_actuel = capital * taux_retrait

    annees = _annees_pour_atteindre(capital, capital_cible, epargne_annuelle, rendement)
    date_fi = None
    if annees is not None:
        jours = int(annees * 365.25)
        date_fi = (datetime.date.today() + datetime.timedelta(days=jours)).isoformat()

    # Sensibilité : ce que 200 € d'épargne mensuelle supplémentaire avancent.
    annees_plus = _annees_pour_atteindre(capital, capital_cible, epargne_annuelle + 2400, rendement)
    gain_mois = None
    if annees is not None and annees_plus is not None:
        gain_mois = round((annees - annees_plus) * 12)

    # Coast FI : le capital à partir duquel ne plus rien verser suffit encore.
    horizon = reglages["horizon_ans"] or 25
    coast_cible = (capital_cible / (1 + rendement) ** horizon) if rendement > 0 else capital_cible
    coast_atteint = capital >= coast_cible

    # Taux d'épargne rapporté au revenu disponible reconstitué.
    revenu_estime = epargne_annuelle + depenses
    taux_epargne = epargne_annuelle / revenu_estime if revenu_estime else 0

    return {
        "reglages": reglages,
        "patrimoine": bilan,
        "frais": couts,
        "capital_cible": round(capital_cible, 2),
        "capital_fi": capital,
        "couverture": round(couverture, 6),
        "revenu_actuel_annuel": round(revenu_actuel, 2),
        "revenu_actuel_mensuel": round(revenu_actuel / 12, 2),
        "depenses_mensuelles": round(depenses / 12, 2),
        "manque": round(max(0.0, capital_cible - capital), 2),
        "annees_restantes": annees,
        "date_independance": date_fi,
        "rendement_retenu": round(rendement, 6),
        "gain_mois_si_plus_200": gain_mois,
        "coast_fi": {
            "cible": round(coast_cible, 2),
            "atteint": coast_atteint,
            "horizon_ans": horizon,
            "manque": round(max(0.0, coast_cible - capital), 2),
        },
        "taux_epargne": round(taux_epargne, 6),
        "epargne_annuelle": round(epargne_annuelle, 2),
        "message": None if annees is not None else
                   "Au rythme actuel, le capital-cible n'est pas atteint en cent ans : "
                   "augmentez l'épargne mensuelle, revoyez les dépenses visées, ou "
                   "vérifiez le rendement réel retenu.",
    }
