"""Comparaison de la performance du portefeuille à des indices de référence.

Deux corrections structurent ce module :

  * les indices sont **reconvertis en euros** avant comparaison. Un indice coté
    en dollars superposé tel quel à un portefeuille en euros se trompe de la
    variation EUR/USD de la période, dans un sens ou dans l'autre ;
  * la courbe du portefeuille est un **TWR en base 100**, pas sa valorisation
    brute. Sinon le moindre versement fait monter le portefeuille sans faire
    monter l'indice, et la comparaison récompense l'épargne au lieu de mesurer
    la gestion.
"""
import datetime
import logging
import math

from backend.analyse import MIN_OBSERVATIONS, _annualisation
from backend.db import get_db
from backend.performance import compute_twr
from backend.risque import ECART_MAX_JOURS
from catalog import BENCHMARK_TICKERS, fx_ticker

log = logging.getLogger("dashboard")


def _serie_close(raw, ticker):
    """Série des clôtures d'un ticker, que yfinance renvoie une ou plusieurs colonnes."""
    close = raw["Close"]
    serie = close[ticker] if hasattr(close, "columns") else close
    return serie.dropna()


def _series_change(yf, devises, debut, fin):
    """
    Séries de taux `devise` -> EUR sur la période : {devise: {date: taux}}.

    Yahoo cote EURUSD=X, soit l'inverse de ce qu'on cherche : on renverse.
    """
    taux = {}
    devises = {d for d in devises if d and d != "EUR"}
    if not devises:
        return taux

    tickers = {fx_ticker(d): d for d in devises}
    try:
        raw = yf.download(" ".join(tickers), start=debut, end=fin,
                          progress=False, auto_adjust=True)
    except Exception as e:
        log.warning(f"Taux de change des indices : {e}")
        return taux
    if raw is None or raw.empty:
        return taux

    for ticker, devise in tickers.items():
        try:
            serie = _serie_close(raw, ticker)
            taux[devise] = {
                (dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]): 1.0 / float(v)
                for dt, v in serie.items() if v
            }
        except Exception as e:
            log.warning(f"Taux EUR/{devise} indisponible : {e}")
    return taux


def _taux_au(serie_taux, date):
    """Taux connu à cette date, sinon le dernier taux antérieur."""
    if not serie_taux:
        return None
    if date in serie_taux:
        return serie_taux[date]
    anterieures = [d for d in serie_taux if d <= date]
    return serie_taux[max(anterieures)] if anterieures else None


def _niveaux_indices(yf, date_debut, fin):
    """
    Niveaux de chaque indice de référence sur la période, reconvertis en euros.

    Retourne `({nom: [(date, valeur)]}, meta, erreur)`. Un indice dont le taux
    de change manque est laissé de côté avec son motif dans `meta` : mieux vaut
    un indice en moins qu'une comparaison fausse de la variation EUR/USD.
    """
    tickers = {nom: cfg["ticker"] for nom, cfg in BENCHMARK_TICKERS.items()}
    try:
        raw = yf.download(" ".join(tickers.values()), start=date_debut, end=fin,
                          progress=False, auto_adjust=True)
    except Exception as e:
        log.warning(f"Téléchargement des indices : {e}")
        return {}, {}, str(e)
    if raw is None or raw.empty:
        return {}, {}, "Données de référence indisponibles."

    change = _series_change(
        yf, {cfg["devise"] for cfg in BENCHMARK_TICKERS.values()}, date_debut, fin
    )

    niveaux, meta = {}, {}
    for nom, cfg in BENCHMARK_TICKERS.items():
        try:
            serie = _serie_close(raw, cfg["ticker"])
            if serie.empty:
                continue

            devise = cfg["devise"]
            if devise != "EUR" and not change.get(devise):
                log.warning(f"Indice {nom} ignoré : taux EUR/{devise} indisponible.")
                meta[nom] = {"devise": devise, "rendement": cfg["rendement"],
                             "ignore": f"taux EUR/{devise} indisponible"}
                continue

            points = []
            for dt, valeur in serie.items():
                date = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                if devise == "EUR":
                    points.append((date, float(valeur)))
                    continue
                taux = _taux_au(change[devise], date)
                if taux:
                    points.append((date, float(valeur) * taux))

            if points:
                niveaux[nom] = points
                meta[nom] = {"devise": devise, "rendement": cfg["rendement"]}
        except Exception as e:
            log.warning(f"Indice {nom} : {e}")
    return niveaux, meta, None


def get_benchmark(period_days=365):
    """
    Portefeuille et indices de référence sur la même période, en base 100.

    Le portefeuille est renvoyé deux fois : en base 100 (TWR, comparable aux
    indices) et en euros (lisible, mais sensible aux versements).
    """
    import yfinance as yf

    with get_db() as db:
        cutoff = (datetime.date.today() - datetime.timedelta(days=period_days)).isoformat()
        historique = db.execute("""
            SELECT date, valorisation total FROM history_daily
            WHERE account_id = 0 AND date >= ? ORDER BY date ASC
        """, (cutoff,)).fetchall()

    if not historique:
        return {"error": "Pas encore d'historique — actualisez les cours pour commencer."}

    capital_depart = historique[0]["total"]
    date_debut = historique[0]["date"]
    if capital_depart <= 0:
        return {"error": "Capital de départ nul sur la période."}

    performance = compute_twr(period_days)

    resultat = {
        "portfolio": [{"date": h["date"], "valeur": h["total"]} for h in historique],
        "portfolio_base100": performance["base100"],
        "twr": performance["twr"],
        "flux_total": performance["flux_total"],
        "capital_depart": capital_depart,
        "date_debut": date_debut,
        "benchmarks": {},
        "meta": {},
    }

    fin = datetime.date.today().isoformat()
    niveaux, meta, erreur = _niveaux_indices(yf, date_debut, fin)
    resultat["meta"] = meta
    if erreur:
        return {**resultat, "error": erreur}

    for nom, points in niveaux.items():
        base = points[0][1]
        if not base:
            continue
        resultat["benchmarks"][nom] = [
            {
                "date": date,
                "base100": round(100 * valeur / base, 4),
                # Même capital de départ que le portefeuille, pour l'axe en euros.
                "valeur": round(capital_depart * valeur / base, 2),
            }
            for date, valeur in points
        ]

    return resultat


# ══════════════════════════════════════════════════════════════
# ÉCART DE SUIVI ET BÊTA
# ══════════════════════════════════════════════════════════════
# Superposer deux courbes dit *si* on a fait mieux ; cela ne dit pas si on a
# fait mieux parce qu'on a pris plus de risque. Ces mesures-là séparent les
# deux : le bêta dit de combien le portefeuille amplifie l'indice, l'alpha ce
# qu'il reste quand cette amplification est retirée, et l'écart de suivi
# combien le chemin a divergé en route.
def _series_alignees(niveaux_a, niveaux_b):
    """
    Rendements des deux séries sur leurs journées communes : (dates, ra, rb).

    Les deux séries sont rendues comparables en recalculant leurs rendements
    sur les **mêmes** journées : un indice cote les jours fériés français, le
    portefeuille n'est photographié que les jours où le serveur tourne, et
    comparer un rendement d'un jour à un rendement de trois n'a pas de sens.
    """
    communes = sorted(set(niveaux_a) & set(niveaux_b))
    dates, ra, rb = [], [], []
    for precedente, courante in zip(communes, communes[1:]):
        ecart = (datetime.date.fromisoformat(courante)
                 - datetime.date.fromisoformat(precedente)).days
        if ecart > ECART_MAX_JOURS:
            continue
        depart_a, depart_b = niveaux_a[precedente], niveaux_b[precedente]
        if depart_a <= 0 or depart_b <= 0:
            continue
        dates.append(courante)
        ra.append(niveaux_a[courante] / depart_a - 1)
        rb.append(niveaux_b[courante] / depart_b - 1)
    return dates, ra, rb


def _compose(rendements):
    """Performance composée d'une série de rendements."""
    total = 1.0
    for r in rendements:
        total *= (1 + r)
    return total - 1


def _capture(rp, rb, hausse=True):
    """
    Captation : part de la performance de l'indice que le portefeuille reprend
    les journées où l'indice monte (ou baisse).

    120 % à la hausse et 80 % à la baisse décrivent un portefeuille qui suit
    l'indice en l'amplifiant quand il monte et en l'amortissant quand il
    tombe — ce que le seul bêta, moyenne des deux, ne distingue pas.
    """
    choisies = [(p, b) for p, b in zip(rp, rb) if (b > 0 if hausse else b < 0)]
    if len(choisies) < 2:
        return None
    reference = _compose([b for _, b in choisies])
    if abs(reference) < 1e-9:
        return None
    return _compose([p for p, _ in choisies]) / reference


def _arrondi(valeur, decimales=4):
    return round(valeur, decimales) if valeur is not None else None


def _mesures(rp, rb, facteur):
    """Bêta, alpha, écart de suivi et captations d'une paire de séries alignées."""
    n = len(rp)
    moyenne_p, moyenne_b = sum(rp) / n, sum(rb) / n
    cov = sum((rp[t] - moyenne_p) * (rb[t] - moyenne_b) for t in range(n)) / (n - 1)
    var_b = sum((r - moyenne_b) ** 2 for r in rb) / (n - 1)
    var_p = sum((r - moyenne_p) ** 2 for r in rp) / (n - 1)

    beta = cov / var_b if var_b > 0 else None
    correlation = (cov / math.sqrt(var_p * var_b)) if var_p > 0 and var_b > 0 else None

    # Écarts quotidiens portefeuille - indice : leur dispersion est l'écart de
    # suivi, leur moyenne la performance active.
    ecarts = [rp[t] - rb[t] for t in range(n)]
    moyenne_ecart = sum(ecarts) / n
    var_ecart = sum((e - moyenne_ecart) ** 2 for e in ecarts) / (n - 1)
    tracking_error = math.sqrt(var_ecart) * math.sqrt(facteur)
    rendement_actif = moyenne_ecart * facteur

    return {
        "nb_observations": n,
        "beta": round(beta, 4) if beta is not None else None,
        # Alpha de Jensen, annualisé : ce que le portefeuille a rendu au-delà
        # de ce que son exposition à l'indice expliquait.
        "alpha": round((moyenne_p - beta * moyenne_b) * facteur, 6) if beta is not None else None,
        "correlation": round(correlation, 4) if correlation is not None else None,
        "r2": round(correlation ** 2, 4) if correlation is not None else None,
        "tracking_error": round(tracking_error, 6),
        "rendement_actif": round(rendement_actif, 6),
        "ratio_information": round(rendement_actif / tracking_error, 3) if tracking_error > 1e-9 else None,
        "capture_hausse": _arrondi(_capture(rp, rb, hausse=True)),
        "capture_baisse": _arrondi(_capture(rp, rb, hausse=False)),
        "perf_portefeuille": round(_compose(rp), 6),
        "perf_indice": round(_compose(rb), 6),
        "ecart": round(_compose(rp) - _compose(rb), 6),
    }


def suivi_indices(period_days=365):
    """
    Bêta, alpha et écart de suivi du portefeuille face à chaque indice.

    Le portefeuille entre dans le calcul par sa courbe de **TWR en base 100**,
    donc corrigée des versements : sans cela un apport se lirait comme une
    journée exceptionnelle, et gonflerait à la fois l'alpha et l'écart de suivi.

    Les indices sont reconvertis en euros avant comparaison (voir le préambule
    du module). Un indice « prix » ignore les dividendes qu'il distribue : le
    portefeuille, lui, les encaisse, et le battre ne prouve donc rien. C'est ce
    que dit `rendement` dans les métadonnées, et l'interface le reprend.
    """
    performance = compute_twr(period_days)
    serie = performance.get("base100") or []

    vide = {
        "periode_jours": period_days, "indices": [], "nb_observations": 0,
        "base_annualisation": None, "minimum_observations": MIN_OBSERVATIONS,
        "meta": {}, "twr": performance.get("twr"),
    }

    if len(serie) < MIN_OBSERVATIONS + 1:
        return {**vide, "message":
                f"{max(0, len(serie) - 1)} journée(s) d'historique : il en faut au moins "
                f"{MIN_OBSERVATIONS} pour qu'un bêta ou un écart de suivi veuille dire "
                "quelque chose. Laissez l'actualisation quotidienne constituer la série."}

    niveaux_portefeuille = {point["date"]: point["valeur"] for point in serie}

    import yfinance as yf

    date_debut, fin = serie[0]["date"], datetime.date.today().isoformat()
    niveaux, meta, erreur = _niveaux_indices(yf, date_debut, fin)
    if erreur:
        return {**vide, "meta": meta, "error": erreur}

    facteur = _annualisation()
    indices, insuffisants = [], []

    for nom in BENCHMARK_TICKERS:
        points = niveaux.get(nom)
        if not points:
            continue
        _, rp, rb = _series_alignees(niveaux_portefeuille, dict(points))
        if len(rp) < MIN_OBSERVATIONS:
            insuffisants.append(f"{nom} ({len(rp)} journée(s) commune(s))")
            continue
        indices.append({
            "nom": nom,
            "devise": meta.get(nom, {}).get("devise", "EUR"),
            "rendement": meta.get(nom, {}).get("rendement", "prix"),
            **_mesures(rp, rb, facteur),
        })

    if not indices:
        return {**vide, "meta": meta, "message":
                "Aucun indice ne partage assez de journées avec l'historique du "
                "portefeuille" + (" : " + ", ".join(insuffisants) if insuffisants else "")
                + ". L'historique est trop court ou trop discontinu."}

    # Le portefeuille est le même pour tous les indices : son nombre
    # d'observations est celui de l'indice le mieux fourni.
    prix_seuls = [i["nom"] for i in indices if i["rendement"] == "prix"]

    return {
        "periode_jours": period_days,
        "nb_observations": max(i["nb_observations"] for i in indices),
        "base_annualisation": facteur,
        "minimum_observations": MIN_OBSERVATIONS,
        "twr": performance.get("twr"),
        "indices": indices,
        "meta": meta,
        "ignores": insuffisants,
        "message": (
            "Indices sans dividendes réinvestis : " + ", ".join(prix_seuls)
            + ". Votre portefeuille encaisse ses dividendes, eux non : les battre de "
              "deux ou trois points par an ne prouve rien."
        ) if prix_seuls else None,
    }
