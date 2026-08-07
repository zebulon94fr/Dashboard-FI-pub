"""Connexion SQLite et schéma.

Le schéma ne connaît aucune enveloppe en particulier : un compte est une ligne
de `accounts` créée par l'utilisateur, et tout le reste (positions, historique,
dividendes) s'y rattache par `account_id`.
"""
import contextlib
import logging
import sqlite3

import config

log = logging.getLogger("dashboard")

SCHEMA = """
-- ── Comptes créés par l'utilisateur ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nom            TEXT    NOT NULL,              -- libellé libre : « PEA Bourse Direct »
    type           TEXT    NOT NULL,              -- pea | cto | per | av | metaux | crypto
    etablissement  TEXT    DEFAULT '',            -- courtier, banque, assureur, plateforme…
    date_ouverture TEXT    DEFAULT '',            -- YYYY-MM-DD — sert aux règles fiscales
    cible_pct      REAL    DEFAULT 0,             -- allocation cible (onglet Rebalancing)
    note           TEXT    DEFAULT '',
    ordre          INTEGER DEFAULT 0,
    created_at     TEXT    DEFAULT (datetime('now'))
);

-- ── Positions ───────────────────────────────────────────────────────────────
-- `cours` et `pru` sont exprimés dans `devise` ; `taux_change` convertit vers
-- l'euro, si bien que `valorisation` et `pv_latent` sont toujours en euros.
CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    nom          TEXT    NOT NULL,
    ticker       TEXT    DEFAULT '',              -- ticker Yahoo Finance (cours automatiques)
    isin         TEXT    DEFAULT '',
    secteur      TEXT    DEFAULT '',              -- libre — alimente le graphique sectoriel
    zone         TEXT    DEFAULT '',              -- libre — alimente le graphique géographique
    quantite     REAL    DEFAULT 0,
    pru          REAL    DEFAULT 0,
    cours        REAL    DEFAULT 0,
    devise       TEXT    DEFAULT 'EUR',
    taux_change  REAL    DEFAULT 1.0,
    valorisation REAL    DEFAULT 0,
    pv_latent    REAL    DEFAULT 0,
    pv_pct       REAL    DEFAULT 0,
    variation    REAL    DEFAULT NULL,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- ── Historique de valorisation ──────────────────────────────────────────────
-- Une ligne par compte et par date, plus une ligne de total (account_id = 0).
CREATE TABLE IF NOT EXISTS history_daily (
    date         TEXT    NOT NULL,                -- YYYY-MM-DD
    account_id   INTEGER NOT NULL DEFAULT 0,      -- 0 = total du portefeuille
    valorisation REAL    DEFAULT 0,
    PRIMARY KEY (date, account_id)
);

CREATE TABLE IF NOT EXISTS history_intraday (
    ts           TEXT    NOT NULL,                -- ISO datetime
    account_id   INTEGER NOT NULL DEFAULT 0,
    valorisation REAL    DEFAULT 0,
    usd_eur      REAL    DEFAULT NULL,
    PRIMARY KEY (ts, account_id)
);

-- ── Cours par position (série temporelle intraday) ─────────────────────────
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    ts          TEXT    NOT NULL DEFAULT (datetime('now')),
    cours       REAL    NOT NULL,
    variation   REAL    DEFAULT NULL
);

-- ── Dividendes et revenus ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dividendes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,                 -- YYYY-MM-DD (date de versement)
    account_id  INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    nom         TEXT    NOT NULL,                 -- nom de la position
    montant     REAL    NOT NULL,                 -- brut en EUR
    montant_net REAL    DEFAULT NULL,             -- net après fiscalité
    note        TEXT    DEFAULT '',
    created_at  TEXT    DEFAULT (datetime('now'))
);

-- ── Index ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_positions_account   ON positions(account_id);
CREATE INDEX IF NOT EXISTS idx_price_history_pos   ON price_history(position_id, ts);
CREATE INDEX IF NOT EXISTS idx_intraday_ts         ON history_intraday(ts);
CREATE INDEX IF NOT EXISTS idx_dividendes_date     ON dividendes(date);
CREATE INDEX IF NOT EXISTS idx_dividendes_position ON dividendes(nom, account_id);
"""


@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect(config.DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
    log.info(f"Base initialisée : {config.DB_FILE}")
