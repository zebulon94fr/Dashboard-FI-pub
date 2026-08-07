"""Récupération des cours via yfinance.

Le moteur est le même pour toutes les enveloppes : une position possède un
ticker Yahoo Finance et une devise, le cours est récupéré dans cette devise
puis converti en euros via le taux de change du moment. Les positions sans
ticker gardent le cours saisi à la main, mais sont revalorisées si leur devise
a bougé.
"""
import datetime
import logging

from backend.db import get_db
from backend.positions import calculs, record_history, record_price_history
from catalog import fx_ticker

log = logging.getLogger("dashboard")


def _import_yfinance():
    import yfinance as yf
    return yf


def _serie(raw, ticker):
    """Série des clôtures d'un ticker, que yfinance renvoie une ou plusieurs colonnes."""
    close = raw["Close"]
    serie = close[ticker] if hasattr(close, "columns") else close
    return serie.dropna()


def _telecharger(yf, tickers):
    """Dernier cours connu pour chaque ticker : {ticker: cours}."""
    if not tickers:
        return {}
    try:
        raw = yf.download(" ".join(tickers), period="1d", interval="1m",
                          progress=False, auto_adjust=True)
        if raw.empty:
            raw = yf.download(" ".join(tickers), period="5d",
                              progress=False, auto_adjust=True)
    except Exception as e:
        log.warning(f"Téléchargement des cours : {e}")
        return {}
    if raw is None or raw.empty:
        return {}

    cours = {}
    for ticker in tickers:
        try:
            serie = _serie(raw, ticker)
            if not serie.empty:
                cours[ticker] = float(serie.iloc[-1])
        except Exception as e:
            log.warning(f"Cours {ticker} indisponible : {e}")
    return cours


def taux_de_change(yf, devises):
    """Taux devise -> EUR pour chaque devise demandée."""
    devises = {d for d in devises if d and d != "EUR"}
    taux = {"EUR": 1.0}
    if not devises:
        return taux

    tickers = {fx_ticker(d): d for d in devises}
    cours = _telecharger(yf, list(tickers))
    for ticker, devise in tickers.items():
        valeur = cours.get(ticker)
        if valeur:
            taux[devise] = round(1.0 / valeur, 6)   # EUR->devise inversé en devise->EUR
        else:
            log.warning(f"Taux de change EUR/{devise} indisponible — dernier taux conservé.")
    return taux


def fetch_quotes():
    """Actualise cours, taux de change et valorisations. Retourne (nb_positions, usd_eur)."""
    yf = _import_yfinance()

    with get_db() as db:
        positions = db.execute("SELECT * FROM positions").fetchall()

    if not positions:
        return 0, None

    taux = taux_de_change(yf, {p["devise"] for p in positions})
    tickers = sorted({p["ticker"].strip() for p in positions if p["ticker"].strip()})
    cours_marche = _telecharger(yf, tickers)

    maintenant = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    actualisees, points = 0, []

    with get_db() as db:
        for p in positions:
            ancien_cours = p["cours"] or 0
            ticker = p["ticker"].strip()
            cours = cours_marche.get(ticker, ancien_cours)
            # Sans taux frais, on conserve celui déjà stocké plutôt que de fausser la valorisation.
            fx = taux.get(p["devise"], p["taux_change"] or 1.0)

            variation = None
            if ticker in cours_marche:
                variation = round((cours - ancien_cours) / ancien_cours, 6) if ancien_cours else 0
                actualisees += 1
                points.append((p["id"], round(cours, 6), variation))

            valo, pv, pct = calculs(p["quantite"], p["pru"], cours, fx)
            db.execute("""
                UPDATE positions SET
                  cours=?, taux_change=?, valorisation=?, pv_latent=?, pv_pct=?,
                  variation=COALESCE(?, variation), updated_at=datetime('now')
                WHERE id=?
            """, (round(cours, 6), fx, valo, pv, pct, variation, p["id"]))

    if points:
        record_price_history(points, maintenant)

    usd_eur = taux.get("USD")
    record_history(usd_eur)

    log.info(f"Cours actualisés : {actualisees}/{len(positions)} positions"
             + (f", USD/EUR={usd_eur:.4f}" if usd_eur else ""))
    return actualisees, usd_eur
