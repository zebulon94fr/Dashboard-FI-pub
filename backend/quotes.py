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

# Variation d'une actualisation à l'autre au-delà de laquelle une division de
# titres est suspectée et vérifiée auprès de yfinance.
SEUIL_SPLIT = 0.35


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


def taux_marche(devise, date=None):
    """
    Taux `devise` -> EUR au marché, ou à une date passée. None si indisponible.

    Appelé quand aucun taux n'est connu pour une devise : mieux vaut une
    requête réseau qu'une valorisation faite comme si la devise était l'euro.
    """
    if devise == "EUR":
        return 1.0
    try:
        yf = _import_yfinance()
    except Exception as e:
        log.warning(f"yfinance indisponible : {e}")
        return None

    ticker = fx_ticker(devise)
    try:
        if date:
            jour = datetime.date.fromisoformat(str(date)[:10])
            # Fenêtre large : un jour férié ou un week-end n'a pas de cotation.
            raw = yf.download(ticker, progress=False, auto_adjust=True,
                              start=(jour - datetime.timedelta(days=8)).isoformat(),
                              end=(jour + datetime.timedelta(days=1)).isoformat())
            if raw is None or raw.empty:
                return None
            serie = _serie(raw, ticker)
            valeur = float(serie.iloc[-1]) if not serie.empty else None
        else:
            valeur = _telecharger(yf, [ticker]).get(ticker)

        if valeur and valeur > 0:
            return round(1.0 / valeur, 6)   # EUR->devise inversé en devise->EUR
    except Exception as e:
        log.warning(f"Taux {devise} indisponible : {e}")
    return None


def _ratio_split(yf, ticker, depuis):
    """
    Ratio cumulé des divisions de titres survenues depuis `depuis`, ou None.

    Un split 4:1 renvoie 4.0 : la quantité détenue est multipliée par 4 et le
    prix de revient unitaire divisé d'autant.
    """
    try:
        splits = yf.Ticker(ticker).splits
        if splits is None or splits.empty:
            return None
        limite = datetime.date.fromisoformat(str(depuis)[:10]) if depuis else None
        ratio = 1.0
        for horodatage, valeur in splits.items():
            jour = horodatage.date() if hasattr(horodatage, "date") else None
            if limite and jour and jour <= limite:
                continue
            if valeur and float(valeur) > 0:
                ratio *= float(valeur)
        return ratio if abs(ratio - 1.0) > 1e-9 else None
    except Exception as e:
        log.warning(f"Divisions de titres {ticker} indisponibles : {e}")
        return None


def _appliquer_split(db, position_id, ratio):
    """
    Répercute une division de titres sur la position et sur son journal.

    Le prix de revient total en euros ne bouge pas — c'est le même argent,
    réparti sur plus de titres — seules la quantité et le prix unitaire changent.
    """
    db.execute(
        "UPDATE positions SET quantite = quantite * ?, pru = pru / ? WHERE id=?",
        (ratio, ratio, position_id),
    )
    db.execute(
        "UPDATE transactions SET quantite = quantite * ?, prix = prix / ? "
        "WHERE position_id=? AND type IN ('achat','vente')",
        (ratio, ratio, position_id),
    )


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
    actualisees, points, splits = 0, [], []

    with get_db() as db:
        for p in positions:
            ancien_cours = p["cours"] or 0
            ticker = p["ticker"].strip()
            cours = cours_marche.get(ticker, ancien_cours)
            # Sans taux frais, on conserve celui déjà stocké plutôt que de fausser la valorisation.
            fx = taux.get(p["devise"], p["taux_change"] or 1.0)
            quantite, pru = p["quantite"], p["pru"]

            variation = None
            if ticker in cours_marche:
                variation = round((cours - ancien_cours) / ancien_cours, 6) if ancien_cours else 0
                actualisees += 1
                points.append((p["id"], round(cours, 6), variation))

                # Un décrochage brutal est le plus souvent une division de
                # titres : le cours est juste, c'est la quantité détenue qui ne
                # l'est plus. On ne corrige que si yfinance confirme le ratio ;
                # sinon c'est un vrai mouvement de marché, qu'on enregistre tel quel.
                if abs(variation) >= SEUIL_SPLIT:
                    ratio = _ratio_split(yf, ticker, p["updated_at"])
                    if ratio:
                        _appliquer_split(db, p["id"], ratio)
                        quantite, pru = quantite * ratio, pru / ratio
                        splits.append((p["nom"], ratio))
                        log.info(f"Division de titres {p['nom']} ({ticker}) : ratio {ratio:g}")
                    else:
                        log.warning(
                            f"{p['nom']} ({ticker}) : {variation:+.1%} en une actualisation, "
                            "sans division de titres connue — cours enregistré tel quel."
                        )

            valo, pv, pct = calculs(quantite, pru, cours, fx, p["cout_eur"])
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
             + (f", USD/EUR={usd_eur:.4f}" if usd_eur else "")
             + (f", {len(splits)} division(s) de titres appliquée(s)" if splits else ""))
    return actualisees, usd_eur, splits
