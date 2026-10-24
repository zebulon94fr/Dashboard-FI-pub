#!/usr/bin/env python3
"""Reprise d'une base portfolioFI dans Dashboard-FI-pub.

Les deux applications n'ont ni le même fichier de base, ni le même schéma :

  • portfolioFI écrit dans `portfolio.db`, Dashboard-FI-pub dans `dashboard.db`.
    Un simple `git pull` ne touche donc pas à l'ancienne base : elle reste
    intacte à côté, et la nouvelle application démarre sur une base vide.
    C'est la raison la plus fréquente d'un dashboard « vide » après mise à jour.

  • l'enveloppe était une chaîne figée dans `positions.compte` (pea, cto, av,
    per_vol, per_obl, crypto, metaux) ; elle est maintenant une ligne de la
    table `accounts`, à laquelle positions, historique et dividendes se
    rattachent par `account_id`.

  • l'historique était large (une colonne par enveloppe) ; il est maintenant
    long (une ligne par compte et par date, `account_id = 0` pour le total).

Ce script lit l'ancienne base en lecture seule et écrit la nouvelle : comptes
créés depuis les enveloppes rencontrées, positions rattachées, historique
pivoté, dividendes et cours historiques repris. Il ne modifie jamais
`portfolio.db`.

Usage :
  python scripts/migrate_portfoliofi.py /chemin/vers/portfolio.db
  python scripts/migrate_portfoliofi.py ... --vers /chemin/vers/dashboard.db
  python scripts/migrate_portfoliofi.py ... --simulation    # n'écrit rien
  python scripts/migrate_portfoliofi.py ... --per-separe    # deux comptes PER
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# `catalog` ne dépend de rien : il est importable avant que la base cible soit
# connue, contrairement à `config` et à tout ce qui en découle.
from catalog import CRYPTO_CATALOG, METAL_CATALOG, classe_par_defaut  # noqa: E402

# ── Correspondance des enveloppes ───────────────────────────────────────────
# Ancienne valeur de `positions.compte` -> (type de compte, libellé proposé).
COMPTES = {
    "pea":     ("pea",    "PEA"),
    "cto":     ("cto",    "Compte-titres"),
    "av":      ("av",     "Assurance-vie"),
    "per_vol": ("per",    "PER — versements volontaires"),
    "per_obl": ("per",    "PER — versements obligatoires"),
    "crypto":  ("crypto", "Cryptoactifs"),
    "metaux":  ("metaux", "Métaux précieux"),
}

ORDRE_ANCIEN = ["pea", "cto", "av", "per_vol", "per_obl", "crypto", "metaux"]

# Colonne de l'ancien historique -> enveloppes qu'elle agrège. L'ancienne base
# ne connaissait qu'un seul montant « per » pour les deux compartiments : la
# colonne ne peut être attribuée à un compte que s'ils sont fusionnés.
COLONNES_HISTORIQUE = {
    "pea": ["pea"], "cto": ["cto"], "av": ["av"],
    "per": ["per_vol", "per_obl"],
    "crypto": ["crypto"], "metaux": ["metaux"],
}

# Les deux tables à forte volumétrie sont purgées au-delà de 90 jours par
# l'application elle-même : en reprendre davantage ne servirait à rien.
RETENTION_JOURS = 90


# ── Lecture de l'ancienne base ──────────────────────────────────────────────
def ouvrir_lecture_seule(chemin):
    """Ouvre la base en lecture seule : la migration ne doit rien y écrire."""
    if not Path(chemin).exists():
        sortir(f"Base introuvable : {chemin}")
    uri = f"file:{Path(chemin).resolve().as_posix()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    return db


def colonnes(db, table):
    return {r["name"] for r in db.execute(f"PRAGMA table_info({table})")}


def verifier_ancienne(db, chemin):
    cols = colonnes(db, "positions")
    if not cols:
        sortir(f"{chemin} ne contient pas de table `positions` : "
               "ce n'est pas une base portfolioFI.")
    if "compte" not in cols:
        if "account_id" in cols:
            sortir(f"{chemin} est déjà au format Dashboard-FI-pub "
                   "(`positions.account_id` existe) : rien à migrer.")
        sortir(f"{chemin} a une table `positions` inattendue : "
               f"colonnes trouvées = {', '.join(sorted(cols))}.")


# ── Enrichissement depuis l'ancien dépôt ────────────────────────────────────
# tickers, secteurs et zones n'existaient pas en base : ils vivaient dans le
# code (tickers.py et static/js/overview.js). S'ils sont encore à côté de
# l'ancienne base, autant les reprendre : sans ticker, une position migrée ne
# sait plus récupérer son cours.
_PAIRE = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1\s*:\s*(['"])((?:\\.|(?!\3).)*)\3""")


def _bloc(texte, nom):
    """Contenu des accolades de l'affectation `nom = { … }`, sinon None."""
    debut = re.search(rf"\b{re.escape(nom)}\b\s*=\s*\{{", texte)
    if not debut:
        return None
    i = debut.end() - 1
    profondeur = 0
    for j in range(i, len(texte)):
        if texte[j] == "{":
            profondeur += 1
        elif texte[j] == "}":
            profondeur -= 1
            if profondeur == 0:
                return texte[i:j + 1]
    return None


def _dict_litteral(texte, nom):
    """Paires chaîne -> chaîne du littéral `nom`. Le code n'est jamais exécuté."""
    bloc = _bloc(texte, nom)
    if not bloc:
        return {}
    desechapper = lambda s: re.sub(r"\\(.)", r"\1", s)
    return {desechapper(m.group(2)): desechapper(m.group(4))
            for m in _PAIRE.finditer(bloc)}


def lire_depot_ancien(dossier):
    """(tickers, secteurs, zones) tels que l'ancienne application les connaissait."""
    tickers, secteurs, zones = {}, {}, {}
    fichier_py = dossier / "tickers.py"
    if fichier_py.exists():
        texte = fichier_py.read_text(encoding="utf-8", errors="replace")
        tickers = _dict_litteral(texte, "TICKERS")
    fichier_js = dossier / "static" / "js" / "overview.js"
    if fichier_js.exists():
        texte = fichier_js.read_text(encoding="utf-8", errors="replace")
        secteurs = _dict_litteral(texte, "SECTEUR_MAP")
        zones = _dict_litteral(texte, "GEO_MAP")
    return tickers, secteurs, zones


# ── Conversion d'une position ───────────────────────────────────────────────
def _cle(nom):
    """Clé de rapprochement : « Or (once) » et « Or » doivent se retrouver."""
    return re.sub(r"\s*\(.*\)\s*$", "", nom or "").strip().lower()


def eur(valeur):
    """Montant à la française : espace pour les milliers, virgule décimale."""
    return f"{valeur:,.2f} €".replace(",", " ").replace(".", ",")


def convertir_position(ancienne, type_compte, catalogues, enrichissement):
    """
    Champs de la nouvelle position, à valorisation inchangée.

    L'ancienne application ne stockait pas ses cours de la même façon selon
    l'enveloppe, et le nouveau schéma n'a qu'une convention : `cours` et `pru`
    sont exprimés dans `devise`, et `taux_change` les convertit en euros. Les
    écarts sont donc redressés ici, position par position.
    """
    crypto_par_nom, metal_par_nom = catalogues
    tickers, secteurs, zones = enrichissement

    extra = {}
    if "extra_json" in ancienne.keys():
        try:
            extra = json.loads(ancienne["extra_json"] or "{}") or {}
        except (ValueError, TypeError):
            extra = {}

    nom = (ancienne["nom"] or "").strip()
    quantite = ancienne["quantite"] or 0.0
    pru = ancienne["pru"] or 0.0
    cours = ancienne["cours"] or 0.0
    cours_usd = ancienne["cours_usd"] if "cours_usd" in ancienne.keys() else None
    taux_ancien = ancienne["taux_change"] or 1.0

    ticker = (extra.get("ticker") or "").strip().upper()
    devise = "EUR"
    taux_change = 1.0
    cout_eur = None
    note = None

    if type_compte == "crypto":
        # L'ancienne application convertissait le cours en euros avant de
        # l'enregistrer, tout en laissant `taux_change` à USD/EUR : la reprendre
        # telle quelle sous-évaluerait la ligne de la variation du dollar.
        # Le nouveau catalogue cote les cryptoactifs en euros, ce qui fait
        # tomber la conversion.
        catalogue = crypto_par_nom.get(_cle(nom))
        if catalogue:
            ticker = ticker or catalogue[0]
        elif not ticker:
            ancien = tickers.get(nom) or ""
            ticker = ancien.replace("-USD", "-EUR")

    elif type_compte == "metaux":
        # Même conversion à l'enregistrement, mais le nouveau catalogue cote
        # les métaux en dollars (contrats à terme). On repasse donc la ligne en
        # dollars à partir du cours USD conservé, et on fige le prix de revient
        # en euros pour que la plus-value ne dérive pas avec le change.
        catalogue = metal_par_nom.get(_cle(nom))
        if catalogue and cours_usd and taux_ancien > 0:
            ticker = ticker or catalogue[0]
            devise = catalogue[1]
            cours = cours_usd
            taux_change = taux_ancien
            cout_eur = round(pru * quantite, 2)
            pru = pru / taux_ancien
            note = "cours repassé en dollars (cotation du nouveau catalogue)"
        else:
            note = "cours conservé en euros — pas de cours automatique sans ticker"

    else:
        # PEA, CTO, AV, PER : `cours` et `pru` étaient déjà dans la devise de la
        # position. Pour le CTO, la devise effective pouvait n'être connue que
        # de `extra_json.deviseCode`, la colonne `devise` restant à sa valeur
        # de saisie.
        devise = (extra.get("deviseCode") or ancienne["devise"] or "EUR").strip().upper()
        if devise != "EUR":
            taux_change = taux_ancien if taux_ancien > 0 else 1.0
            if taux_ancien <= 0:
                note = f"aucun taux {devise}->EUR en base — taux 1,0 à corriger"
        if not ticker:
            ticker = (tickers.get(nom) or "").strip().upper()

    # Une devise en euros avec un taux différent de 1 vaut une valorisation
    # fausse : le cas se produisait dès qu'une ligne avait été actualisée.
    if devise == "EUR":
        taux_change = 1.0

    return {
        "id": ancienne["id"],
        "nom": nom,
        "ticker": ticker,
        "isin": (ancienne["isin"] or "").strip().upper(),
        "secteur": secteurs.get(nom, ""),
        "zone": zones.get(nom, ""),
        "classe": classe_par_defaut(type_compte),
        "groupe": "",
        "ter": 0.0,
        "quantite": quantite,
        "pru": pru,
        "cours": cours,
        "devise": devise,
        "taux_change": taux_change,
        "cout_eur": cout_eur,
    }, note


# ── Migration ───────────────────────────────────────────────────────────────
def sortir(message, code=1):
    print(f"Erreur : {message}", file=sys.stderr)
    sys.exit(code)


def migrer(args):
    ancienne = ouvrir_lecture_seule(args.source)
    verifier_ancienne(ancienne, args.source)

    # `config` lit DASHBOARD_DB à l'import : la cible doit être fixée avant.
    if args.vers:
        os.environ["DASHBOARD_DB"] = str(Path(args.vers).resolve())
    import config  # noqa: PLC0415
    from backend.accounts import create_account  # noqa: PLC0415
    from backend.db import get_db, init_db  # noqa: PLC0415
    from backend.positions import calculs  # noqa: PLC0415

    cible = Path(config.DB_FILE)
    if cible.resolve() == Path(args.source).resolve():
        sortir("la source et la cible sont le même fichier.")

    print(f"Source : {Path(args.source).resolve()}")
    print(f"Cible  : {cible.resolve()}{'   (simulation)' if args.simulation else ''}")

    # Une simulation ne doit pas même créer le fichier cible : on ne l'ouvre
    # que s'il existe déjà, et en lecture seule.
    if args.simulation:
        deja = 0
        if cible.exists():
            temoin = ouvrir_lecture_seule(cible)
            if colonnes(temoin, "accounts"):
                deja = temoin.execute("SELECT COUNT(*) n FROM accounts").fetchone()["n"]
            temoin.close()
    else:
        init_db(signaler_ancienne=False)
        with get_db() as db:
            deja = db.execute("SELECT COUNT(*) n FROM accounts").fetchone()["n"]
    if deja:
        sortir(f"{cible} contient déjà {deja} compte(s). La reprise ne sait pas "
               "fusionner : déplacez ce fichier (ou indiquez une autre cible "
               "avec --vers) puis relancez.")

    catalogues = (
        {_cle(n): (t, d) for n, t, d in CRYPTO_CATALOG},
        {_cle(n): (t, d) for n, t, d in METAL_CATALOG},
    )
    dossier_ancien = Path(args.source).resolve().parent
    if args.sans_enrichissement:
        enrichissement = ({}, {}, {})
    else:
        enrichissement = lire_depot_ancien(dossier_ancien)
        tickers, secteurs, zones = enrichissement
        if tickers or secteurs:
            print(f"Dépôt portfolioFI trouvé dans {dossier_ancien} : "
                  f"{len(tickers)} ticker(s), {len(secteurs)} secteur(s), "
                  f"{len(zones)} zone(s) repris.")
        else:
            print(f"Pas de tickers/secteurs exploitables dans {dossier_ancien} "
                  "— les positions arriveront sans ticker.")

    # ── Comptes ─────────────────────────────────────────────────────────────
    presentes = {r["compte"] for r in
                 ancienne.execute("SELECT DISTINCT compte FROM positions")}
    inconnues = presentes - set(COMPTES)
    if inconnues:
        print(f"Enveloppes inconnues ignorées : {', '.join(sorted(inconnues))}")
    enveloppes = [c for c in ORDRE_ANCIEN if c in presentes]
    if not enveloppes:
        sortir("aucune position à reprendre dans l'ancienne base.")

    comptes = {}            # ancienne enveloppe -> account_id
    libelles = {}           # account_id -> libellé
    fusion_per = not args.per_separe and {"per_vol", "per_obl"} <= presentes
    for rang, enveloppe in enumerate(enveloppes, start=1):
        type_compte, libelle = COMPTES[enveloppe]
        if fusion_per and enveloppe == "per_obl":
            comptes[enveloppe] = comptes["per_vol"]
            continue
        if fusion_per and enveloppe == "per_vol":
            libelle = "PER"
        if args.simulation:
            account_id = -rang
        else:
            account_id = create_account({"nom": libelle, "type": type_compte,
                                         "ordre": rang})
        comptes[enveloppe] = account_id
        libelles[account_id] = libelle

    print()
    for enveloppe in enveloppes:
        n = ancienne.execute("SELECT COUNT(*) n FROM positions WHERE compte=?",
                             (enveloppe,)).fetchone()["n"]
        print(f"  {enveloppe:<8} -> compte « {libelles[comptes[enveloppe]]} » "
              f"({n} position(s))")

    # ── Positions ───────────────────────────────────────────────────────────
    lignes, remarques, ecarts = [], [], []
    metaux_en_usd = set()
    for ancienne_pos in ancienne.execute("SELECT * FROM positions ORDER BY id"):
        enveloppe = ancienne_pos["compte"]
        if enveloppe not in comptes:
            continue
        type_compte = COMPTES[enveloppe][0]
        champs, remarque = convertir_position(ancienne_pos, type_compte,
                                              catalogues, enrichissement)
        valo, pv, pct = calculs(champs["quantite"], champs["pru"], champs["cours"],
                                champs["taux_change"], champs["cout_eur"])
        ancienne_valo = ancienne_pos["valorisation"] or 0.0
        if abs(valo - ancienne_valo) > 0.01:
            ecarts.append((champs["nom"], ancienne_valo, valo))
        if remarque:
            remarques.append((champs["nom"], remarque))
        if type_compte == "metaux" and champs["devise"] != "EUR":
            metaux_en_usd.add(champs["id"])
        lignes.append((champs, comptes[enveloppe], valo, pv, pct,
                       ancienne_pos["variation"]))

    if not args.simulation:
        with get_db() as db:
            for champs, account_id, valo, pv, pct, variation in lignes:
                db.execute("""
                    INSERT INTO positions
                      (id, account_id, nom, ticker, isin, secteur, zone, classe,
                       groupe, ter, quantite, pru, cours, devise, taux_change,
                       cout_eur, valorisation, pv_latent, pv_pct, variation)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (champs["id"], account_id, champs["nom"], champs["ticker"],
                      champs["isin"], champs["secteur"], champs["zone"],
                      champs["classe"], champs["groupe"], champs["ter"],
                      champs["quantite"], round(champs["pru"], 6), champs["cours"],
                      champs["devise"], champs["taux_change"], champs["cout_eur"],
                      valo, pv, pct, variation))

    print(f"\n{len(lignes)} position(s) reprise(s), "
          f"{sum(1 for l in lignes if l[0]['ticker'])} avec ticker.")
    total = round(sum(l[2] for l in lignes), 2)
    print(f"Valorisation totale : {eur(total)}")

    # ── Historique ──────────────────────────────────────────────────────────
    # Une colonne « per » attribuée à deux comptes serait une invention : dans
    # ce cas la courbe par compte est omise, le total restant exact.
    cible_colonne = {}
    for colonne, origines in COLONNES_HISTORIQUE.items():
        ids = {comptes[o] for o in origines if o in comptes}
        if len(ids) == 1:
            cible_colonne[colonne] = ids.pop()
    omises = [c for c in COLONNES_HISTORIQUE if c not in cible_colonne
              and any(o in comptes for o in COLONNES_HISTORIQUE[c])]

    cols_hist = colonnes(ancienne, "history_daily")
    jours = ancienne.execute("SELECT * FROM history_daily ORDER BY date").fetchall()
    rows_daily = []
    for jour in jours:
        valeurs = {c: (jour[c] or 0.0) for c in COLONNES_HISTORIQUE if c in cols_hist}
        total_jour = jour["total"] or round(sum(valeurs.values()), 2)
        rows_daily.append((jour["date"], 0, round(total_jour, 2)))
        for colonne, valeur in valeurs.items():
            if colonne in cible_colonne:
                rows_daily.append((jour["date"], cible_colonne[colonne],
                                   round(valeur, 2)))

    cols_intra = colonnes(ancienne, "history_intraday")
    intra = ancienne.execute(
        "SELECT * FROM history_intraday "
        f"WHERE ts >= datetime('now','-{RETENTION_JOURS} days') ORDER BY ts"
    ).fetchall()
    rows_intra = []
    for point in intra:
        # L'application écrit ses horodatages avec un « T » : on homogénéise,
        # sinon la série se trie dans deux ordres différents.
        ts = (point["ts"] or "").replace(" ", "T")
        if not ts:
            continue
        valeurs = {c: (point[c] or 0.0) for c in COLONNES_HISTORIQUE if c in cols_intra}
        total_point = point["total"] or round(sum(valeurs.values()), 2)
        usd_eur = point["usd_eur"] if "usd_eur" in point.keys() else None
        rows_intra.append((ts, 0, round(total_point, 2), usd_eur))
        for colonne, valeur in valeurs.items():
            if colonne in cible_colonne:
                rows_intra.append((ts, cible_colonne[colonne], round(valeur, 2), None))

    if not args.simulation and (rows_daily or rows_intra):
        with get_db() as db:
            db.executemany(
                "INSERT OR REPLACE INTO history_daily (date, account_id, valorisation)"
                " VALUES (?,?,?)", rows_daily)
            db.executemany(
                "INSERT OR REPLACE INTO history_intraday (ts, account_id, valorisation, usd_eur)"
                " VALUES (?,?,?,?)", rows_intra)

    if jours:
        print(f"{len(jours)} jour(s) d'historique repris "
              f"({jours[0]['date']} -> {jours[-1]['date']}).")
    else:
        print("Aucun historique quotidien dans l'ancienne base.")
    print(f"{len(intra)} point(s) intraday des {RETENTION_JOURS} derniers jours.")
    if omises:
        print(f"Courbe par compte omise pour : {', '.join(omises)} "
              "(montant agrégé dans l'ancienne base, non ventilable).")

    # ── Cours historiques ───────────────────────────────────────────────────
    ids_connus = {champs["id"] for champs, *_ in lignes}
    rows_prix = []
    for point in ancienne.execute(
        "SELECT * FROM price_history "
        f"WHERE ts >= datetime('now','-{RETENTION_JOURS} days') ORDER BY ts"
    ):
        if point["position_id"] not in ids_connus:
            continue
        cours = point["cours"]
        if point["position_id"] in metaux_en_usd:
            # La position est passée en dollars : sa série doit l'être aussi.
            cours = point["cours_usd"] if "cours_usd" in point.keys() else None
            if cours is None:
                continue
        rows_prix.append((point["position_id"], (point["ts"] or "").replace(" ", "T"),
                          cours, point["variation"]))
    if not args.simulation and rows_prix:
        with get_db() as db:
            db.executemany(
                "INSERT INTO price_history (position_id, ts, cours, variation)"
                " VALUES (?,?,?,?)", rows_prix)
    print(f"{len(rows_prix)} cours historique(s) repris.")

    # ── Dividendes ──────────────────────────────────────────────────────────
    rows_div, div_orphelins = [], 0
    for div in ancienne.execute("SELECT * FROM dividendes ORDER BY date, id"):
        account_id = comptes.get(div["compte"])
        if account_id is None:
            div_orphelins += 1
            continue
        rows_div.append((div["id"], div["date"], account_id, div["nom"],
                         div["montant"], div["montant_net"], div["note"] or ""))
    if not args.simulation and rows_div:
        with get_db() as db:
            db.executemany(
                "INSERT INTO dividendes (id, date, account_id, nom, montant,"
                " montant_net, note) VALUES (?,?,?,?,?,?,?)", rows_div)
    print(f"{len(rows_div)} dividende(s) repris." +
          (f" {div_orphelins} rattaché(s) à une enveloppe absente, ignoré(s)."
           if div_orphelins else ""))

    # ── Contrôles et suites à donner ────────────────────────────────────────
    if remarques:
        print("\nPositions redressées :")
        for nom, remarque in remarques[:15]:
            print(f"  • {nom} — {remarque}")
        if len(remarques) > 15:
            print(f"  … et {len(remarques) - 15} autre(s)")

    if ecarts:
        print("\nValorisations recalculées différentes de celles enregistrées "
              "(cours jamais actualisé, ou devise redressée) :")
        for nom, avant, apres in ecarts[:10]:
            print(f"  • {nom} : {eur(avant)} -> {eur(apres)}")
        if len(ecarts) > 10:
            print(f"  … et {len(ecarts) - 10} autre(s)")

    if jours:
        dernier = jours[-1]["total"] or 0.0
        if dernier and abs(dernier - total) / dernier > 0.05:
            print(f"\nLe dernier total historique ({eur(dernier)}) s'écarte de "
                  f"plus de 5 % de la valorisation des positions ({eur(total)}) : "
                  "l'ancienne base n'avait probablement pas été actualisée le "
                  "même jour.")

    print("""
À faire dans l'application après la reprise :
  1. Comptes  : renseigner la date d'ouverture du PEA et de l'assurance-vie.
                C'est elle qui déclenche les seuils de 5 et 8 ans de l'onglet
                Fiscalité ; sans elle, l'avantage fiscal n'est pas calculé.
  2. Mouvements : l'ancienne application ne tenait pas de journal. Tant qu'il
                est vide, le TWR et la performance annualisée comptent tout
                versement passé comme de la performance, et le TRI reste
                indisponible. Saisir au moins les versements et retraits
                importants corrige les deux.
  3. Positions : vérifier la classe d'actifs, proposée d'après l'enveloppe, et
                le TER des fonds (onglet Frais).
  4. Profil   : onglet Indépendance, renseigner dépenses et épargne annuelles.
""")

    if args.simulation:
        print("Simulation : rien n'a été écrit. Relancez sans --simulation.")
    else:
        print(f"Reprise terminée. Démarrez l'application : elle lira {cible}.")
        print("Pensez à copier settings.json (mot de passe, clés) : le format "
              "est identique dans les deux versions.")


def main():
    parser = argparse.ArgumentParser(
        description="Reprend une base portfolioFI dans Dashboard-FI-pub.")
    parser.add_argument("source", help="ancienne base portfolioFI (portfolio.db)")
    parser.add_argument("--vers", help="base cible (défaut : celle de l'application)")
    parser.add_argument("--simulation", action="store_true",
                        help="analyse et affiche le bilan sans rien écrire")
    parser.add_argument("--per-separe", action="store_true",
                        help="deux comptes PER au lieu d'un seul ; l'historique "
                             "PER, agrégé dans l'ancienne base, n'est alors "
                             "conservé que dans le total")
    parser.add_argument("--sans-enrichissement", action="store_true",
                        help="ne pas relire tickers.py ni overview.js de "
                             "l'ancien dépôt")
    migrer(parser.parse_args())


if __name__ == "__main__":
    main()
