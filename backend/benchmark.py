"""Comparaison de la performance du portefeuille à des indices de référence."""
import datetime
import logging

from backend.db import get_db
from catalog import BENCHMARK_TICKERS

log = logging.getLogger("dashboard")


def get_benchmark(period_days=365):
    """
    Indices de référence sur la même période que l'historique, normalisés sur le
    même capital de départ que le portefeuille (base 100 en euros).
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

    resultat = {
        "portfolio": [{"date": h["date"], "valeur": h["total"]} for h in historique],
        "capital_depart": capital_depart,
        "date_debut": date_debut,
        "benchmarks": {},
    }

    try:
        raw = yf.download(
            " ".join(BENCHMARK_TICKERS.values()),
            start=date_debut,
            end=datetime.date.today().isoformat(),
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return {**resultat, "error": "Données de référence indisponibles."}

        for nom, ticker in BENCHMARK_TICKERS.items():
            try:
                close = raw["Close"]
                serie = (close[ticker] if hasattr(close, "columns") else close).dropna()
                if serie.empty:
                    continue
                base = float(serie.iloc[0])
                resultat["benchmarks"][nom] = [
                    {
                        "date": dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10],
                        "valeur": round(capital_depart * float(valeur) / base, 2),
                    }
                    for dt, valeur in serie.items()
                ]
            except Exception as e:
                log.warning(f"Indice {nom} : {e}")
    except Exception as e:
        log.warning(f"Téléchargement des indices : {e}")
        resultat["error"] = str(e)

    return resultat
