"""Analyse du portefeuille : risque, concentration, devises et contribution.

Le dashboard savait dire combien on avait gagné, jamais ce qu'on avait risqué
pour l'obtenir, ni d'où venait le gain. Ce module comble les deux manques à
partir de données déjà en base : la série quotidienne de `history_daily`, les
devises et taux portés par chaque position, et le prix de revient figé à
l'achat que le journal des mouvements a rendu fiable.

Toutes les mesures de risque se calculent sur des rendements **corrigés des
flux** : sans cela un versement passerait pour une journée exceptionnelle et
gonflerait la volatilité comme la performance.
"""
import datetime
import math

from backend.db import get_db
from backend.performance import flux_par_date
from catalog import CLASSES_ACTIFS, ORDRE_CLASSES

# 252 séances de bourse par an. Les cryptoactifs cotent en continu : le
# portefeuille qui en contient est annualisé sur 365 jours (voir _annualisation).
SEANCES_PAR_AN = 252
JOURS_PAR_AN = 365

# Taux sans risque par défaut, servant de référence au ratio de Sharpe. Il est
# affiché à côté du ratio : sans lui, le chiffre n'est pas interprétable.
TAUX_SANS_RISQUE = 0.025


# ══════════════════════════════════════════════════════════════
# SÉRIE DE RENDEMENTS
# ══════════════════════════════════════════════════════════════
def rendements_quotidiens(period_days=365):
    """
    Rendements journaliers corrigés des flux : [(date, rendement)].

    Même formule que le TWR — (V_fin - flux) / V_début - 1 — appliquée jour par
    jour. Une journée sans valorisation de la veille est ignorée plutôt
    qu'assimilée à un rendement nul.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=period_days)).isoformat()
    with get_db() as db:
        historique = db.execute("""
            SELECT date, valorisation FROM history_daily
            WHERE account_id = 0 AND date >= ? ORDER BY date ASC
        """, (cutoff,)).fetchall()

    if len(historique) < 2:
        return []

    flux = flux_par_date(None, cutoff)
    series, precedent = [], historique[0]["valorisation"]
    for ligne in historique[1:]:
        courant = ligne["valorisation"]
        if precedent > 0:
            rendement = (courant - flux.get(ligne["date"], 0.0)) / precedent - 1
            if rendement > -1:
                series.append((ligne["date"], rendement))
        precedent = courant
    return series


def _ecart_type(valeurs):
    """Écart-type d'échantillon (n-1), ou None sous deux observations."""
    if len(valeurs) < 2:
        return None
    moyenne = sum(valeurs) / len(valeurs)
    variance = sum((v - moyenne) ** 2 for v in valeurs) / (len(valeurs) - 1)
    return math.sqrt(variance)


def _annualisation():
    """365 jours si le portefeuille contient des cryptoactifs, 252 sinon."""
    with get_db() as db:
        crypto = db.execute("""
            SELECT 1 FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.valorisation > 0 AND (p.classe = 'crypto' OR a.type = 'crypto') LIMIT 1
        """).fetchone()
    return JOURS_PAR_AN if crypto else SEANCES_PAR_AN


# ══════════════════════════════════════════════════════════════
# RISQUE
# ══════════════════════════════════════════════════════════════
def max_drawdown(period_days=365):
    """
    Plus forte baisse depuis un sommet, avec sa date et sa durée de récupération.

    Plus parlant que la volatilité : c'est la perte qu'il a fallu supporter sans
    vendre. Calculé sur la valorisation brute — un retrait creuserait
    artificiellement le creux, aussi les flux sont-ils retirés au passage.
    """
    cutoff = (datetime.date.today() - datetime.timedelta(days=period_days)).isoformat()
    with get_db() as db:
        historique = db.execute("""
            SELECT date, valorisation FROM history_daily
            WHERE account_id = 0 AND date >= ? ORDER BY date ASC
        """, (cutoff,)).fetchall()

    if len(historique) < 2:
        return None

    # On rejoue la courbe en base 100 hors flux : c'est la performance pure qui
    # intéresse, pas les mouvements du compte en banque.
    flux = flux_par_date(None, cutoff)
    base, courbe = 100.0, [(historique[0]["date"], 100.0)]
    precedent = historique[0]["valorisation"]
    for ligne in historique[1:]:
        courant = ligne["valorisation"]
        if precedent > 0:
            rendement = (courant - flux.get(ligne["date"], 0.0)) / precedent - 1
            if rendement > -1:
                base *= (1 + rendement)
        courbe.append((ligne["date"], base))
        precedent = courant

    sommet, date_sommet = courbe[0][1], courbe[0][0]
    pire, date_creux, debut_creux = 0.0, None, None
    for date, valeur in courbe:
        if valeur > sommet:
            sommet, date_sommet = valeur, date
        baisse = valeur / sommet - 1 if sommet else 0
        if baisse < pire:
            pire, date_creux, debut_creux = baisse, date, date_sommet

    if not date_creux:
        return {"drawdown": 0.0, "date_creux": None, "date_sommet": None, "recupere": True, "jours_baisse": 0}

    # Récupération : première date après le creux qui retrouve le sommet perdu.
    niveau_sommet = next((v for d, v in courbe if d == debut_creux), None)
    date_reprise = next((d for d, v in courbe if d > date_creux and niveau_sommet and v >= niveau_sommet), None)

    debut = datetime.date.fromisoformat(debut_creux)
    creux = datetime.date.fromisoformat(date_creux)
    return {
        "drawdown": round(pire, 6),
        "date_sommet": debut_creux,
        "date_creux": date_creux,
        "jours_baisse": (creux - debut).days,
        "recupere": date_reprise is not None,
        "date_reprise": date_reprise,
        "jours_recuperation": (datetime.date.fromisoformat(date_reprise) - creux).days if date_reprise else None,
    }


def metriques_risque(period_days=365):
    """Volatilité annualisée, perte maximale et ratio de Sharpe."""
    series = rendements_quotidiens(period_days)
    rendements = [r for _, r in series]

    if len(rendements) < 2:
        return {
            "volatilite": None, "sharpe": None, "drawdown": None,
            "nb_observations": len(rendements),
            "message": "Deux journées d'historique au minimum — actualisez les cours quelques jours.",
        }

    facteur = _annualisation()
    ecart = _ecart_type(rendements)
    volatilite = ecart * math.sqrt(facteur) if ecart else None

    # Performance annualisée composée sur la période observée.
    compose = 1.0
    for r in rendements:
        compose *= (1 + r)
    annees = len(rendements) / facteur
    perf_annualisee = (compose ** (1 / annees) - 1) if annees > 0 and compose > 0 else None

    sharpe = None
    if volatilite and volatilite > 0 and perf_annualisee is not None:
        sharpe = (perf_annualisee - TAUX_SANS_RISQUE) / volatilite

    return {
        "volatilite": round(volatilite, 6) if volatilite else None,
        "perf_annualisee": round(perf_annualisee, 6) if perf_annualisee is not None else None,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "taux_sans_risque": TAUX_SANS_RISQUE,
        "base_annualisation": facteur,
        "drawdown": max_drawdown(period_days),
        "nb_observations": len(rendements),
        "periode_jours": period_days,
        "message": None if len(rendements) >= 20 else
                   f"Seulement {len(rendements)} journées observées : ces mesures "
                   "demandent plusieurs semaines d'historique pour vouloir dire quelque chose.",
    }


# ══════════════════════════════════════════════════════════════
# CONCENTRATION
# ══════════════════════════════════════════════════════════════
def concentration():
    """
    Poids des plus grosses lignes et indice de Herfindahl.

    Le HHI est traduit en « équivalent nombre de lignes équipondérées » : un
    HHI de 0,25 se lit « aussi concentré qu'un portefeuille de 4 lignes », ce
    qui se comprend sans avoir à expliquer l'indice.

    La transparisation regroupe les positions partageant un même `groupe` : deux
    ETF World logés sur deux enveloppes différentes comptent alors pour une
    seule exposition, ce qu'ils sont en réalité.
    """
    with get_db() as db:
        positions = db.execute("""
            SELECT p.nom, p.groupe, p.valorisation, a.nom compte, a.type compte_type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.valorisation > 0 ORDER BY p.valorisation DESC
        """).fetchall()

    total = sum(p["valorisation"] for p in positions)
    if not total:
        return {"total": 0, "lignes": [], "expositions": [], "hhi": None,
                "message": "Aucune position valorisée."}

    lignes = [{
        "nom": p["nom"], "compte": p["compte"], "compte_type": p["compte_type"],
        "groupe": p["groupe"] or "", "valorisation": p["valorisation"],
        "poids": round(p["valorisation"] / total, 6),
    } for p in positions]

    # Transparisation : un `groupe` renseigné fusionne les doublons.
    agrege = {}
    for p in positions:
        cle = (p["groupe"] or "").strip() or f"__{p['nom']}"
        entree = agrege.setdefault(cle, {
            "nom": (p["groupe"] or "").strip() or p["nom"],
            "transparise": bool((p["groupe"] or "").strip()),
            "valorisation": 0.0, "lignes": [],
        })
        entree["valorisation"] += p["valorisation"]
        entree["lignes"].append(f"{p['nom']} ({p['compte']})")

    expositions = sorted(agrege.values(), key=lambda e: e["valorisation"], reverse=True)
    for e in expositions:
        e["poids"] = round(e["valorisation"] / total, 6)
        e["nb_lignes"] = len(e["lignes"])

    poids = [e["valorisation"] / total for e in expositions]
    hhi = sum(p * p for p in poids)

    return {
        "total": round(total, 2),
        "lignes": lignes[:15],
        "expositions": expositions[:15],
        "nb_lignes": len(lignes),
        "nb_expositions": len(expositions),
        "poids_top1": round(poids[0], 6) if poids else 0,
        "poids_top5": round(sum(poids[:5]), 6),
        "poids_top10": round(sum(poids[:10]), 6),
        "hhi": round(hhi, 6),
        "lignes_equivalentes": round(1 / hhi, 2) if hhi else None,
        "regroupees": sum(1 for e in expositions if e["nb_lignes"] > 1),
    }


# ══════════════════════════════════════════════════════════════
# DEVISES ET ATTRIBUTION DE CHANGE
# ══════════════════════════════════════════════════════════════
def exposition_devises():
    """
    Répartition par devise et décomposition du gain en effet marché / effet change.

    La décomposition est exacte quand le prix de revient en euros est connu :

        valorisation - cout = (cours - pru) x q x taux_achat   (effet marché)
                            + cours x q x (taux_actuel - taux_achat)  (effet change)

    Le taux d'achat est déduit du prix de revient figé par le journal. Sans lui,
    la ligne est comptée dans l'effet marché : on ne peut pas attribuer ce qu'on
    ne sait pas dater.
    """
    with get_db() as db:
        positions = db.execute("""
            SELECT nom, devise, quantite, pru, cours, taux_change, cout_eur,
                   valorisation, pv_latent
            FROM positions WHERE valorisation > 0
        """).fetchall()

    total = sum(p["valorisation"] for p in positions)
    if not total:
        return {"total": 0, "devises": [], "attribution": None,
                "message": "Aucune position valorisée."}

    par_devise, effet_marche, effet_change, non_attribue = {}, 0.0, 0.0, 0
    for p in positions:
        devise = p["devise"] or "EUR"
        entree = par_devise.setdefault(devise, {
            "devise": devise, "valorisation": 0.0, "pv_latent": 0.0,
            "nb_positions": 0, "taux": p["taux_change"],
        })
        entree["valorisation"] += p["valorisation"]
        entree["pv_latent"] += p["pv_latent"] or 0
        entree["nb_positions"] += 1

        cout_local = (p["pru"] or 0) * (p["quantite"] or 0)
        if devise == "EUR" or not cout_local or p["cout_eur"] is None:
            effet_marche += p["pv_latent"] or 0
            if devise != "EUR" and p["cout_eur"] is None:
                non_attribue += 1
            continue

        taux_achat = p["cout_eur"] / cout_local
        valeur_locale = (p["cours"] or 0) * (p["quantite"] or 0)
        effet_marche += (valeur_locale - cout_local) * taux_achat
        effet_change += valeur_locale * ((p["taux_change"] or 1) - taux_achat)

    devises = sorted(par_devise.values(), key=lambda d: d["valorisation"], reverse=True)
    for d in devises:
        d["poids"] = round(d["valorisation"] / total, 6)
        d["valorisation"] = round(d["valorisation"], 2)
        d["pv_latent"] = round(d["pv_latent"], 2)

    hors_euro = sum(d["valorisation"] for d in devises if d["devise"] != "EUR")

    return {
        "total": round(total, 2),
        "devises": devises,
        "part_hors_euro": round(hors_euro / total, 6) if total else 0,
        "attribution": {
            "effet_marche": round(effet_marche, 2),
            "effet_change": round(effet_change, 2),
            "total": round(effet_marche + effet_change, 2),
            "positions_non_attribuees": non_attribue,
        },
        "message": (f"{non_attribue} position(s) en devise sans prix de revient daté : "
                    "leur gain est compté en effet marché faute de taux d'achat connu. "
                    "Enregistrez leurs achats dans le journal pour l'attribuer.")
                   if non_attribue else None,
    }


# ══════════════════════════════════════════════════════════════
# CONTRIBUTION À LA PERFORMANCE
# ══════════════════════════════════════════════════════════════
def contributions():
    """
    Contribution de chaque ligne à la performance du portefeuille.

    Un classement par plus-value absolue mélange taille et mérite : une ligne à
    +3 % qui pèse 30 % du portefeuille passe devant une ligne à +60 % qui en
    pèse 2 %. La contribution en points — plus-value de la ligne rapportée au
    capital investi total — répond à la vraie question : qu'est-ce qui a fait
    bouger le patrimoine ? Elle se somme exactement à la performance globale,
    ce qui la rend vérifiable.
    """
    with get_db() as db:
        positions = db.execute("""
            SELECT p.nom, p.classe, p.pv_latent, p.pv_pct, p.valorisation,
                   COALESCE(p.cout_eur, p.pru * p.quantite * p.taux_change) cout,
                   a.nom compte, a.type compte_type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.quantite > 0
        """).fetchall()

    investi = sum(p["cout"] or 0 for p in positions)
    if not investi:
        return {"investi": 0, "lignes": [], "total_points": 0,
                "message": "Aucun prix de revient connu."}

    lignes = [{
        "nom": p["nom"], "compte": p["compte"], "compte_type": p["compte_type"],
        "classe": p["classe"] or "autre",
        "cout": round(p["cout"] or 0, 2),
        "poids_investi": round((p["cout"] or 0) / investi, 6),
        "performance": round(p["pv_pct"] or 0, 6),
        "pv_latent": round(p["pv_latent"] or 0, 2),
        "contribution": round((p["pv_latent"] or 0) / investi, 6),
    } for p in positions]

    lignes.sort(key=lambda l: l["contribution"], reverse=True)
    total_points = sum(l["contribution"] for l in lignes)

    return {
        "investi": round(investi, 2),
        "lignes": lignes,
        "total_points": round(total_points, 6),
        "meilleures": lignes[:5],
        "pires": [l for l in reversed(lignes) if l["contribution"] < 0][:5],
    }


# ══════════════════════════════════════════════════════════════
# RÉPARTITION PAR CLASSE D'ACTIFS
# ══════════════════════════════════════════════════════════════
def repartition_classes():
    """Valorisation par classe d'actifs, toutes enveloppes confondues."""
    with get_db() as db:
        rows = db.execute("""
            SELECT COALESCE(NULLIF(p.classe, ''), 'autre') classe,
                   SUM(p.valorisation) valorisation,
                   SUM(COALESCE(p.cout_eur, p.pru * p.quantite * p.taux_change)) investi,
                   SUM(p.pv_latent) pv_latent,
                   COUNT(*) nb_positions
            FROM positions p WHERE p.valorisation > 0
            GROUP BY classe
        """).fetchall()
        cibles = {r["classe"]: r["cible_pct"]
                  for r in db.execute("SELECT classe, cible_pct FROM allocations_classes")}

    total = sum(r["valorisation"] for r in rows) or 0
    par_classe = {r["classe"]: dict(r) for r in rows}

    resultat = []
    for classe in ORDRE_CLASSES:
        donnees = par_classe.get(classe)
        cible = cibles.get(classe, 0)
        if not donnees and not cible:
            continue
        valorisation = (donnees or {}).get("valorisation", 0) or 0
        resultat.append({
            "classe": classe,
            "label": CLASSES_ACTIFS[classe]["label"],
            "couleur": CLASSES_ACTIFS[classe]["couleur"],
            "valorisation": round(valorisation, 2),
            "investi": round((donnees or {}).get("investi", 0) or 0, 2),
            "pv_latent": round((donnees or {}).get("pv_latent", 0) or 0, 2),
            "nb_positions": (donnees or {}).get("nb_positions", 0),
            "poids": round(valorisation / total, 6) if total else 0,
            "cible_pct": cible,
        })

    return {"total": round(total, 2), "classes": resultat,
            "total_cibles": round(sum(cibles.values()), 2)}


def analyse_complete(period_days=365):
    """Payload de GET /api/analyse."""
    return {
        "risque": metriques_risque(period_days),
        "concentration": concentration(),
        "devises": exposition_devises(),
        "contributions": contributions(),
        "classes": repartition_classes(),
    }
