"""Contribution au risque et corrélations, ligne par ligne.

L'onglet Analyse disait déjà ce que le portefeuille avait risqué *en bloc* :
une volatilité, une perte maximale. Il ne disait pas **d'où vient ce risque**,
et c'est une question différente de celle du poids. Une ligne qui pèse 10 % du
capital mais bouge trois fois plus que le reste et monte quand tout monte peut
porter 30 % du risque : elle est la vraie décision du portefeuille, et rien ne
le montrait.

La décomposition repose sur une identité exacte, pas sur une approximation :

    σ_p = Σ_i w_i × β_i × σ_p          avec β_i = cov(i, p) / σ_p²

autrement dit la somme des contributions vaut la volatilité du portefeuille,
ce qui la rend vérifiable — et c'est ce que le total du tableau affiche.

Deux précautions font toute la validité du calcul :

  * les rendements se calculent sur le **prix** (cours converti en euros), pas
    sur la valorisation. La valorisation bouge à chaque achat ou vente : un
    renforcement passerait pour une journée à +40 % et ferait exploser la
    volatilité comme les corrélations de la ligne concernée ;
  * la matrice de covariance est bâtie sur des **dates communes** à toutes les
    lignes retenues. Calculer chaque paire sur son propre échantillon donne une
    matrice incohérente, dont la variance du portefeuille peut sortir négative.
    Les lignes trop lacunaires sont donc écartées, et le tableau dit quelle part
    du portefeuille la mesure couvre réellement.
"""
import datetime
import math

from backend.analyse import MIN_OBSERVATIONS, _annualisation
from backend.db import get_db
from catalog import TYPES_PASSIF

# Part des journées de la fenêtre qu'une ligne doit couvrir pour entrer dans la
# matrice. En dessous, elle imposerait son propre trou à toutes les autres.
COUVERTURE_MIN = 0.80

# Au-delà de cet écart entre deux clôtures, le rendement n'est pas un rendement
# quotidien : c'est le mouvement de toute une période, et le mêler aux autres
# gonflerait la volatilité. Sept jours laissent passer les week-ends et les
# ponts, pas une semaine d'arrêt du serveur.
ECART_MAX_JOURS = 7

# Nombre de lignes affichées dans la matrice de corrélation. Au-delà, le tableau
# devient illisible — la contribution au risque, elle, porte sur toutes.
MAX_CORRELATIONS = 12

SANS_PASSIF = "a.type NOT IN (%s)" % ",".join("?" * len(TYPES_PASSIF))
PARAMS_PASSIF = tuple(TYPES_PASSIF)


# ══════════════════════════════════════════════════════════════
# SÉRIES DE PRIX
# ══════════════════════════════════════════════════════════════
def _charger(period_days):
    """Clôtures et signalement de chaque position : (series, infos)."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=period_days)).isoformat()
    with get_db() as db:
        lignes = db.execute(f"""
            SELECT cq.date, cq.position_id, cq.prix_eur, cq.source
            FROM cours_quotidiens cq
            JOIN positions p ON p.id = cq.position_id
            JOIN accounts a ON a.id = p.account_id
            WHERE cq.date >= ? AND cq.prix_eur > 0
              AND p.valorisation > 0 AND {SANS_PASSIF}
            ORDER BY cq.date ASC
        """, (cutoff, *PARAMS_PASSIF)).fetchall()

        positions = db.execute(f"""
            SELECT p.id, p.nom, p.devise, p.valorisation, p.classe,
                   a.nom compte, a.type compte_type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.valorisation > 0 AND {SANS_PASSIF}
        """, PARAMS_PASSIF).fetchall()

    series, sources = {}, {}
    for ligne in lignes:
        series.setdefault(ligne["position_id"], {})[ligne["date"]] = ligne["prix_eur"]
        compteur = sources.setdefault(ligne["position_id"], {"marche": 0, "total": 0})
        compteur["total"] += 1
        if ligne["source"] == "marche":
            compteur["marche"] += 1

    infos = {}
    for p in positions:
        compteur = sources.get(p["id"], {"marche": 0, "total": 0})
        infos[p["id"]] = {
            "nom": p["nom"], "compte": p["compte"], "compte_type": p["compte_type"],
            "classe": p["classe"] or "autre", "devise": p["devise"] or "EUR",
            "valorisation": p["valorisation"],
            "part_marche": (compteur["marche"] / compteur["total"]) if compteur["total"] else 0.0,
        }
    return series, infos


def _dates_communes(series, retenues):
    """Journées où toutes les lignes retenues ont un prix, du plus ancien au plus récent."""
    if not retenues:
        return []
    commun = set(series[retenues[0]])
    for position_id in retenues[1:]:
        commun &= set(series[position_id])
    return sorted(commun)


def _rendements(serie, dates):
    """
    Rendements d'une ligne d'une date commune à la suivante.

    Les écarts trop longs sont rendus en None plutôt qu'en rendement : on garde
    l'alignement des séries entre elles, et l'appelant écarte l'observation pour
    toutes les lignes à la fois.
    """
    sortie = []
    for precedente, courante in zip(dates, dates[1:]):
        ecart = (datetime.date.fromisoformat(courante)
                 - datetime.date.fromisoformat(precedente)).days
        depart = serie[precedente]
        if ecart > ECART_MAX_JOURS or depart <= 0:
            sortie.append(None)
        else:
            sortie.append(serie[courante] / depart - 1)
    return sortie


# ══════════════════════════════════════════════════════════════
# COVARIANCE
# ══════════════════════════════════════════════════════════════
def _covariance(colonnes):
    """Matrice de covariance d'échantillon (n-1) d'une liste de séries alignées."""
    n = len(colonnes[0])
    moyennes = [sum(col) / n for col in colonnes]
    ecarts = [[v - moyennes[i] for v in col] for i, col in enumerate(colonnes)]
    taille = len(colonnes)
    matrice = [[0.0] * taille for _ in range(taille)]
    for i in range(taille):
        for j in range(i, taille):
            valeur = sum(ecarts[i][t] * ecarts[j][t] for t in range(n)) / (n - 1)
            matrice[i][j] = matrice[j][i] = valeur
    return matrice, moyennes


# ══════════════════════════════════════════════════════════════
# CONTRIBUTION AU RISQUE
# ══════════════════════════════════════════════════════════════
def contribution_risque(period_days=365):
    """
    Décomposition de la volatilité du portefeuille ligne par ligne.

    Retourne toujours un dictionnaire de même forme : quand la mesure est
    impossible, `message` dit pourquoi et ce qu'il manque, plutôt que de
    renvoyer une erreur que l'interface aurait à interpréter.
    """
    series, infos = _charger(period_days)

    vide = {
        "periode_jours": period_days, "nb_observations": 0, "lignes": [],
        "correlations": None, "ecartees": [], "couverture": 0,
        "volatilite_portefeuille": None, "volatilite_moyenne_ponderee": None,
        "ratio_diversification": None, "base_annualisation": None,
        "minimum_observations": MIN_OBSERVATIONS,
    }

    valeur_totale = sum(i["valorisation"] for i in infos.values())
    if not series or not valeur_totale:
        return {**vide, "message":
                "Aucune clôture quotidienne enregistrée. Cette page se remplit à mesure que "
                "les cours sont actualisés ; pour démarrer tout de suite depuis l'historique "
                "déjà en base : python scripts/amorcer_clotures.py"}

    toutes_dates = sorted({d for serie in series.values() for d in serie})
    seuil = max(2, int(COUVERTURE_MIN * len(toutes_dates)))

    retenues, ecartees = [], []
    for position_id, info in infos.items():
        couverture = len(series.get(position_id, {}))
        if couverture >= seuil:
            retenues.append(position_id)
        else:
            ecartees.append({
                "nom": info["nom"], "compte": info["compte"],
                "poids": round(info["valorisation"] / valeur_totale, 6),
                "motif": (f"{couverture} clôture(s) sur {len(toutes_dates)} journées"
                          if couverture else "aucune clôture enregistrée"),
            })
    ecartees.sort(key=lambda e: e["poids"], reverse=True)

    dates = _dates_communes(series, retenues)
    if len(dates) < MIN_OBSERVATIONS + 1:
        return {**vide, "ecartees": ecartees, "nb_observations": max(0, len(dates) - 1),
                "message":
                f"{max(0, len(dates) - 1)} rendement(s) commun(s) à toutes les lignes retenues : "
                f"il en faut au moins {MIN_OBSERVATIONS} pour une matrice de covariance qui "
                "veuille dire quelque chose. Laissez l'actualisation quotidienne constituer "
                "l'historique — cette page apparaîtra d'elle-même."}

    # Rendements alignés : une journée dont l'écart est trop long est retirée
    # pour toutes les lignes, afin que la matrice reste cohérente.
    brut = {position_id: _rendements(series[position_id], dates) for position_id in retenues}
    gardes = [t for t in range(len(dates) - 1)
              if all(brut[position_id][t] is not None for position_id in retenues)]

    if len(gardes) < MIN_OBSERVATIONS:
        return {**vide, "ecartees": ecartees, "nb_observations": len(gardes),
                "message":
                f"{len(gardes)} journée(s) exploitable(s) après retrait des trous de plus de "
                f"{ECART_MAX_JOURS} jours : il en faut {MIN_OBSERVATIONS}. L'historique est "
                "trop discontinu pour en tirer un risque — vérifiez que l'actualisation "
                "quotidienne tourne (voir scripts/refresh_quotes.sh)."}

    colonnes = [[brut[position_id][t] for t in gardes] for position_id in retenues]
    matrice, _ = _covariance(colonnes)

    valeur_retenue = sum(infos[position_id]["valorisation"] for position_id in retenues)
    poids = [infos[position_id]["valorisation"] / valeur_retenue for position_id in retenues]

    # Variance du portefeuille : wᵗΣw, et les covariances croisées sont bien ce
    # qui fait qu'un portefeuille bouge moins que la moyenne de ses lignes.
    sigma_w = [sum(matrice[i][j] * poids[j] for j in range(len(poids)))
               for i in range(len(poids))]
    variance = sum(poids[i] * sigma_w[i] for i in range(len(poids)))
    if variance <= 0:
        return {**vide, "ecartees": ecartees, "nb_observations": len(gardes),
                "message":
                "Variance nulle sur la période : aucune des lignes retenues n'a bougé. "
                "C'est le cas d'un portefeuille dont les cours sont tous saisis à la main — "
                "renseignez leur ticker pour que le dashboard les suive."}

    facteur = _annualisation()
    sigma_jour = math.sqrt(variance)
    sigma_annuel = sigma_jour * math.sqrt(facteur)

    lignes = []
    for i, position_id in enumerate(retenues):
        info = infos[position_id]
        variance_i = matrice[i][i]
        sigma_i = math.sqrt(variance_i) if variance_i > 0 else 0.0
        # β de la ligne face au portefeuille : cov(i, p) / variance(p).
        beta = sigma_w[i] / variance
        contribution = poids[i] * beta * sigma_annuel
        lignes.append({
            "position_id": position_id,
            "nom": info["nom"], "compte": info["compte"], "compte_type": info["compte_type"],
            "classe": info["classe"], "devise": info["devise"],
            "valorisation": round(info["valorisation"], 2),
            "poids": round(poids[i], 6),
            "volatilite": round(sigma_i * math.sqrt(facteur), 6),
            "beta": round(beta, 4),
            "correlation": round(sigma_w[i] / (sigma_i * sigma_jour), 4) if sigma_i > 0 else None,
            "contribution": round(contribution, 6),
            "part_risque": round(poids[i] * beta, 6),
            "part_marche": round(info["part_marche"], 3),
        })
    lignes.sort(key=lambda l: l["part_risque"], reverse=True)

    # Volatilité moyenne pondérée : celle qu'aurait le portefeuille si tout
    # bougeait ensemble. Son écart avec la vraie mesure *est* la diversification.
    vol_ponderee = sum(l["poids"] * l["volatilite"] for l in lignes)

    # Une ligne au cours saisi à la main ne bouge pas : elle ne porte aucun
    # risque mesurable, mais elle occupe sa part du capital. Elle dilue donc la
    # volatilité du portefeuille d'autant, et il faut le dire avec un chiffre —
    # c'est le cas d'un bien immobilier ou d'un fonds non coté, qui peuvent
    # peser l'essentiel du patrimoine.
    saisies = [l for l in lignes if l["part_marche"] < 0.5]
    poids_saisi = sum(l["poids"] for l in saisies)

    return {
        "periode_jours": period_days,
        "nb_observations": len(gardes),
        "nb_journees": len(dates),
        "minimum_observations": MIN_OBSERVATIONS,
        "base_annualisation": facteur,
        "volatilite_portefeuille": round(sigma_annuel, 6),
        "volatilite_moyenne_ponderee": round(vol_ponderee, 6),
        "ratio_diversification": round(vol_ponderee / sigma_annuel, 3) if sigma_annuel else None,
        "couverture": round(valeur_retenue / valeur_totale, 6),
        "valeur_couverte": round(valeur_retenue, 2),
        "lignes": lignes,
        "correlations": _correlations(lignes, retenues, matrice),
        "ecartees": ecartees,
        "poids_cours_saisi": round(poids_saisi, 6),
        "message": (
            "Cours saisis à la main sur : "
            + ", ".join(l["nom"] for l in saisies[:4])
            + ("…" if len(saisies) > 4 else "")
            + f" — soit {poids_saisi:.0%} du portefeuille mesuré. Un cours immobile n'a pas de "
              "volatilité : ces lignes ne portent aucun risque ici, la volatilité du "
              "portefeuille s'en trouve diluée d'autant, et la part de risque des autres "
              "lignes est mécaniquement surestimée. Renseignez leur ticker pour que le "
              "dashboard les suive."
        ) if saisies else None,
    }


def _correlations(lignes, retenues, matrice):
    """Matrice de corrélation des plus grosses lignes, et les paires extrêmes."""
    index = {position_id: i for i, position_id in enumerate(retenues)}
    choisies = sorted(lignes, key=lambda l: l["poids"], reverse=True)[:MAX_CORRELATIONS]
    if len(choisies) < 2:
        return None

    def correlation(a, b):
        i, j = index[a["position_id"]], index[b["position_id"]]
        denominateur = math.sqrt(matrice[i][i] * matrice[j][j])
        return round(matrice[i][j] / denominateur, 4) if denominateur > 0 else None

    grille = [[1.0 if a is b else correlation(a, b) for b in choisies] for a in choisies]

    paires = []
    for i, a in enumerate(choisies):
        for b in choisies[i + 1:]:
            valeur = correlation(a, b)
            if valeur is not None:
                paires.append({"a": a["nom"], "b": b["nom"], "correlation": valeur})
    paires.sort(key=lambda p: p["correlation"], reverse=True)

    return {
        "noms": [l["nom"] for l in choisies],
        "matrice": grille,
        "plus_correlees": paires[:5],
        "moins_correlees": list(reversed(paires[-5:])),
        "nb_lignes": len(choisies),
        "total_lignes": len(lignes),
    }
