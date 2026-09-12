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
    nom            TEXT    NOT NULL,              -- libellé libre : « PEA — mon courtier »
    type           TEXT    NOT NULL,              -- pea | cto | per | av | metaux | crypto
    etablissement  TEXT    DEFAULT '',            -- courtier, banque, assureur, plateforme…
    date_ouverture TEXT    DEFAULT '',            -- YYYY-MM-DD — sert aux règles fiscales
    cible_pct      REAL    DEFAULT 0,             -- allocation cible (onglet Rebalancing)
    frais_pct      REAL    DEFAULT 0,             -- frais de gestion annuels de l'enveloppe, en %
    note           TEXT    DEFAULT '',
    ordre          INTEGER DEFAULT 0,
    created_at     TEXT    DEFAULT (datetime('now'))
);

-- ── Positions ───────────────────────────────────────────────────────────────
-- `cours` et `pru` sont exprimés dans `devise` ; `taux_change` convertit vers
-- l'euro, si bien que `valorisation` et `pv_latent` sont toujours en euros.
--
-- `cout_eur` est le prix de revient réellement supporté en euros, figé au jour
-- de l'achat. Il ne doit jamais être recalculé au taux du moment : sinon le
-- gain de change sur le capital disparaît des comptes. Il vaut NULL pour une
-- position saisie à la main sans journal de mouvements ; le prix de revient
-- est alors estimé à `pru * quantite * taux_change`, faute de mieux.
CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    nom          TEXT    NOT NULL,
    ticker       TEXT    DEFAULT '',              -- ticker Yahoo Finance (cours automatiques)
    isin         TEXT    DEFAULT '',
    secteur      TEXT    DEFAULT '',              -- libre — alimente le graphique sectoriel
    zone         TEXT    DEFAULT '',              -- libre — alimente le graphique géographique
    classe       TEXT    DEFAULT '',              -- classe d'actifs (catalog.CLASSES_ACTIFS)
    groupe       TEXT    DEFAULT '',              -- sous-jacent commun, pour la transparisation
    ter          REAL    DEFAULT 0,               -- frais courants du support (TER), en %
    quantite     REAL    DEFAULT 0,
    pru          REAL    DEFAULT 0,
    cours        REAL    DEFAULT 0,
    devise       TEXT    DEFAULT 'EUR',
    taux_change  REAL    DEFAULT 1.0,
    cout_eur     REAL    DEFAULT NULL,            -- prix de revient en euros, figé à l'achat
    valorisation REAL    DEFAULT 0,
    pv_latent    REAL    DEFAULT 0,
    pv_pct       REAL    DEFAULT 0,
    variation    REAL    DEFAULT NULL,
    updated_at   TEXT    DEFAULT (datetime('now'))
);

-- ── Journal des mouvements ──────────────────────────────────────────────────
-- La source de vérité du portefeuille. Quantité, prix de revient moyen pondéré
-- et plus-values réalisées d'une position en découlent (voir transactions.py) ;
-- les flux datés alimentent le TWR et le TRI (voir performance.py).
--
-- `montant_eur` est toujours positif : c'est `type` qui porte le sens du flux
-- (achat et versement font entrer de l'argent, vente, retrait et frais en font
-- sortir). `nom` duplique le libellé de la position pour que le journal reste
-- lisible après la suppression de celle-ci.
CREATE TABLE IF NOT EXISTS transactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,                -- YYYY-MM-DD
    account_id   INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    position_id  INTEGER REFERENCES positions(id) ON DELETE SET NULL,
    type         TEXT    NOT NULL,                -- achat|vente|versement|retrait|frais
    nom          TEXT    DEFAULT '',
    quantite     REAL    DEFAULT 0,
    prix         REAL    DEFAULT 0,               -- prix unitaire, dans `devise`
    devise       TEXT    DEFAULT 'EUR',
    taux_change  REAL    DEFAULT 1.0,             -- devise -> EUR au jour de l'opération
    frais        REAL    DEFAULT 0,               -- en euros
    montant_eur  REAL    DEFAULT 0,               -- montant du mouvement en euros, frais compris
    note         TEXT    DEFAULT '',
    created_at   TEXT    DEFAULT (datetime('now'))
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

-- ── Allocation cible par classe d'actifs ────────────────────────────────────
-- Pilotée toutes enveloppes confondues : une classe d'actifs traverse les
-- comptes, là où `accounts.cible_pct` ne décrit qu'une répartition fiscale.
CREATE TABLE IF NOT EXISTS allocations_classes (
    classe     TEXT PRIMARY KEY,
    cible_pct  REAL DEFAULT 0
);

-- ── Réglages du profil ──────────────────────────────────────────────────────
-- Dépenses, épargne et horizon : ce que le dashboard ne peut pas déduire des
-- cours, et sans quoi aucune métrique d'indépendance financière n'est calculable.
CREATE TABLE IF NOT EXISTS reglages (
    cle    TEXT PRIMARY KEY,
    valeur TEXT
);

-- ── Index ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_positions_account   ON positions(account_id);
CREATE INDEX IF NOT EXISTS idx_price_history_pos   ON price_history(position_id, ts);
CREATE INDEX IF NOT EXISTS idx_intraday_ts         ON history_intraday(ts);
CREATE INDEX IF NOT EXISTS idx_dividendes_date     ON dividendes(date);
CREATE INDEX IF NOT EXISTS idx_dividendes_position ON dividendes(nom, account_id);
CREATE INDEX IF NOT EXISTS idx_tx_date             ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_tx_position         ON transactions(position_id, date);
CREATE INDEX IF NOT EXISTS idx_tx_account          ON transactions(account_id, date);
"""

# Colonnes ajoutées après la première version du schéma. SQLite ne sait pas
# faire « ADD COLUMN IF NOT EXISTS » : on regarde la table avant d'écrire.
MIGRATIONS = [
    ("positions", "cout_eur", "REAL DEFAULT NULL"),
    ("positions", "classe", "TEXT DEFAULT ''"),
    ("positions", "groupe", "TEXT DEFAULT ''"),
    ("positions", "ter", "REAL DEFAULT 0"),
    ("accounts", "frais_pct", "REAL DEFAULT 0"),
]


def _migrate(db):
    for table, colonne, definition in MIGRATIONS:
        existantes = {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}
        if colonne in existantes:
            continue
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")
            log.info(f"Migration : {table}.{colonne} ajoutée")
        except sqlite3.OperationalError as e:
            # Plusieurs workers gunicorn démarrent en parallèle et migrent la
            # même base : celui qui arrive second doit constater que la colonne
            # existe déjà, pas refuser de démarrer.
            if "duplicate column" not in str(e).lower():
                raise
            log.info(f"Migration : {table}.{colonne} déjà ajoutée par un autre processus")


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
        _migrate(db)
    log.info(f"Base initialisée : {config.DB_FILE}")
