"""Agrégats du portefeuille : totaux, répartitions, meilleures et pires positions."""
from backend.accounts import list_accounts
from backend.db import get_db
from catalog import ACCOUNT_TYPES


def get_stats():
    comptes = list_accounts()

    total = sum(c["valorisation"] for c in comptes)
    investi = sum(c["investi"] for c in comptes)
    pv_latent = sum(c["pv_latent"] for c in comptes)

    par_type = {}
    for c in comptes:
        agrege = par_type.setdefault(c["type"], {
            "type": c["type"],
            "label": ACCOUNT_TYPES.get(c["type"], {}).get("label", c["type"]),
            "couleur": ACCOUNT_TYPES.get(c["type"], {}).get("couleur", "#8b949e"),
            "valorisation": 0, "investi": 0, "pv_latent": 0, "nb_comptes": 0,
        })
        agrege["valorisation"] += c["valorisation"]
        agrege["investi"] += c["investi"]
        agrege["pv_latent"] += c["pv_latent"]
        agrege["nb_comptes"] += 1
    for agrege in par_type.values():
        agrege["pv_pct"] = (agrege["pv_latent"] / agrege["investi"]) if agrege["investi"] else 0

    with get_db() as db:
        intraday = db.execute("""
            SELECT ts, valorisation total, usd_eur
            FROM history_intraday
            WHERE account_id = 0 AND ts >= datetime('now','-7 days')
            ORDER BY ts ASC
        """).fetchall()

        daily = db.execute("""
            SELECT date, valorisation total FROM history_daily
            WHERE account_id = 0 ORDER BY date ASC
        """).fetchall()

        top_pv = db.execute("""
            SELECT p.nom, p.pv_latent, p.pv_pct, p.valorisation, a.nom compte, a.type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.pru > 0 AND p.quantite > 0
            ORDER BY p.pv_latent DESC LIMIT 5
        """).fetchall()

        worst_pv = db.execute("""
            SELECT p.nom, p.pv_latent, p.pv_pct, p.valorisation, a.nom compte, a.type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.pru > 0 AND p.quantite > 0
            ORDER BY p.pv_latent ASC LIMIT 5
        """).fetchall()

        perf_24h = db.execute("""
            SELECT
              (SELECT valorisation FROM history_intraday
               WHERE account_id = 0 ORDER BY ts DESC LIMIT 1) now_total,
              (SELECT valorisation FROM history_intraday
               WHERE account_id = 0 AND ts <= datetime('now','-1 day')
               ORDER BY ts DESC LIMIT 1) prev_total
        """).fetchone()

        best_day = db.execute("""
            SELECT date, valorisation total,
                   valorisation - LAG(valorisation) OVER (ORDER BY date) delta
            FROM history_daily WHERE account_id = 0
            ORDER BY delta DESC LIMIT 1
        """).fetchone()
        worst_day = db.execute("""
            SELECT date, valorisation total,
                   valorisation - LAG(valorisation) OVER (ORDER BY date) delta
            FROM history_daily WHERE account_id = 0
            ORDER BY delta ASC LIMIT 1
        """).fetchone()

        snap_count = db.execute(
            "SELECT COUNT(*) n FROM history_intraday WHERE account_id = 0"
        ).fetchone()

    maintenant = perf_24h["now_total"] if perf_24h else None
    precedent = perf_24h["prev_total"] if perf_24h else None
    var24h = round(maintenant - precedent, 2) if maintenant and precedent else None
    var24h_pct = round((maintenant - precedent) / precedent, 6) if maintenant and precedent else None

    return {
        "current": {
            "total": round(total, 2),
            "investi": round(investi, 2),
            "pv_latent_total": round(pv_latent, 2),
            "pv_pct": round(pv_latent / investi, 6) if investi else 0,
            "nb_comptes": len(comptes),
            "nb_positions": sum(c["nb_positions"] for c in comptes),
        },
        "par_compte": [
            {k: c[k] for k in
             ("id", "nom", "type", "type_label", "valorisation", "investi", "pv_latent", "pv_pct", "nb_positions")}
            for c in comptes
        ],
        "par_type": list(par_type.values()),
        "intraday": [dict(r) for r in intraday],
        "daily": [dict(r) for r in daily],
        "top_pv": [dict(r) for r in top_pv],
        "worst_pv": [dict(r) for r in worst_pv],
        "var24h": var24h,
        "var24h_pct": var24h_pct,
        "best_day": dict(best_day) if best_day else None,
        "worst_day": dict(worst_day) if worst_day else None,
        "snap_count": snap_count["n"] if snap_count else 0,
    }
