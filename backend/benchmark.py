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

from backend.db import get_db
from backend.performance import compute_twr
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

    try:
        fin = datetime.date.today().isoformat()
        tickers = {nom: cfg["ticker"] for nom, cfg in BENCHMARK_TICKERS.items()}
        raw = yf.download(" ".join(tickers.values()), start=date_debut, end=fin,
                          progress=False, auto_adjust=True)
        if raw is None or raw.empty:
            return {**resultat, "error": "Données de référence indisponibles."}

        change = _series_change(
            yf, {cfg["devise"] for cfg in BENCHMARK_TICKERS.values()}, date_debut, fin
        )

        for nom, cfg in BENCHMARK_TICKERS.items():
            try:
                serie = _serie_close(raw, cfg["ticker"])
                if serie.empty:
                    continue

                devise = cfg["devise"]
                if devise != "EUR" and not change.get(devise):
                    log.warning(f"Indice {nom} ignoré : taux EUR/{devise} indisponible.")
                    resultat["meta"][nom] = {
                        "devise": devise, "rendement": cfg["rendement"],
                        "ignore": f"taux EUR/{devise} indisponible",
                    }
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

                if not points:
                    continue

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
                resultat["meta"][nom] = {"devise": devise, "rendement": cfg["rendement"]}
            except Exception as e:
                log.warning(f"Indice {nom} : {e}")
    except Exception as e:
        log.warning(f"Téléchargement des indices : {e}")
        resultat["error"] = str(e)

    return resultat
