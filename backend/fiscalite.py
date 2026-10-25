"""Règles fiscales françaises appliquées aux enveloppes du portefeuille.

L'onglet Fiscalité simule depuis toujours un retrait, enveloppe par enveloppe,
dans le navigateur. Ce module porte les mêmes règles côté serveur, pour les
questions qu'une page ne sait pas poser seule : d'où sortir une somme au
moindre coût, ce qu'il reste d'abattement cette année, et quelles cessions
déclarer.

Un avertissement vaut pour tout le module : ce sont des **estimations**. Elles
ignorent la situation personnelle — tranche marginale, quotient familial,
option pour le barème — et ne remplacent pas un conseil. Elles servent à
comparer deux retraits entre eux, pas à remplir une déclaration à l'aveugle.
"""
import datetime

from backend.db import get_db
from catalog import (
    ACCOUNT_TYPES,
    AV_ABATTEMENT_COUPLE,
    AV_ABATTEMENT_SEUL,
    AV_IR_REDUIT,
    CRYPTO_SEUIL_CESSIONS,
    IMMO_IR,
    METAUX_ABATTEMENT_AN,
    METAUX_FRANCHISE_ANS,
    METAUX_PLUS_VALUE,
    PFU,
    PRELEVEMENTS_SOCIAUX,
)

JOURS_PAR_AN = 365.25


# ══════════════════════════════════════════════════════════════
# DURÉE DE DÉTENTION
# ══════════════════════════════════════════════════════════════
def anciennete(compte, a_la_date=None):
    """Années écoulées depuis l'ouverture du compte, ou None si inconnue."""
    date_ouverture = (compte.get("date_ouverture") or "").strip()
    if not date_ouverture:
        return None
    try:
        ouverture = datetime.date.fromisoformat(date_ouverture)
    except ValueError:
        return None
    reference = a_la_date or datetime.date.today()
    return max(0.0, (reference - ouverture).days / JOURS_PAR_AN)


def seuil_atteint(compte, a_la_date=None):
    """
    Le seuil de durée de l'enveloppe est-il franchi ? None si indécidable.

    L'indécision compte : sans date d'ouverture, présumer le seuil atteint
    ferait miroiter une exonération qui n'existe peut-être pas.
    """
    seuil = ACCOUNT_TYPES.get(compte.get("type"), {}).get("seuil_ans")
    if not seuil:
        return None
    ans = anciennete(compte, a_la_date)
    return None if ans is None else ans >= seuil


# ══════════════════════════════════════════════════════════════
# ABATTEMENTS POUR DURÉE DE DÉTENTION
# ══════════════════════════════════════════════════════════════
def abattement_metaux(annees):
    """5 % par an au-delà de deux ans, exonération totale à 22 ans."""
    if annees is None:
        return 0.0
    return min(1.0, max(0.0, (annees - METAUX_FRANCHISE_ANS) * METAUX_ABATTEMENT_AN))


def abattements_immobilier(annees):
    """
    Abattements de plus-value immobilière, impôt et prélèvements séparés.

    Les deux barèmes ne coïncident pas : l'impôt sur le revenu s'efface au bout
    de 22 ans, les prélèvements sociaux seulement à 30 ans. Les confondre
    annoncerait une exonération totale huit ans trop tôt.
    """
    if annees is None:
        return {"ir": 0.0, "ps": 0.0}

    ir = 0.0
    if annees > 5:
        ir = (min(annees, 21) - 5) * 0.06 + (0.04 if annees >= 22 else 0.0)
    if annees >= 22:
        ir = 1.0

    ps = 0.0
    if annees > 5:
        ps = (min(annees, 21) - 5) * 0.0165
        if annees >= 22:
            ps += 0.016
        if annees > 22:
            ps += (min(annees, 30) - 22) * 0.09
    if annees >= 30:
        ps = 1.0

    return {"ir": min(1.0, max(0.0, ir)), "ps": min(1.0, max(0.0, ps))}


# ══════════════════════════════════════════════════════════════
# COÛT D'UN RETRAIT
# ══════════════════════════════════════════════════════════════
def part_gains(compte):
    """
    Part de plus-value dans la valorisation de l'enveloppe.

    Un rachat partiel n'est pas prélevé sur les seuls gains : il emporte une
    quote-part de capital et une quote-part de gains, dans la proportion où
    ils se trouvent. C'est cette proportion-là qui est imposée.
    """
    valorisation = compte.get("valorisation") or 0
    if valorisation <= 0:
        return 0.0
    return max(0.0, min(1.0, (compte.get("pv_latent") or 0) / valorisation))


def cout_retrait(compte, montant, couple=False, abattement_restant=None):
    """
    Impôt estimé sur un retrait, et ce qu'il en reste net.

    `abattement_restant` permet d'enchaîner plusieurs rachats d'assurance vie
    dans la même année sans réutiliser l'abattement déjà consommé.
    """
    type_compte = compte.get("type")
    modele = ACCOUNT_TYPES.get(type_compte, {}).get("modele_fiscal", "flat")
    montant = max(0.0, float(montant or 0))
    gain = montant * part_gains(compte)
    atteint = seuil_atteint(compte)
    ans = anciennete(compte)

    detail, notes = [], []

    if modele == "pea":
        if atteint:
            impot = gain * PRELEVEMENTS_SOCIAUX
            detail.append(("Prélèvements sociaux (17,2 %)", impot))
            notes.append("Après 5 ans : exonéré d'impôt sur le revenu, "
                         "et le retrait partiel ne clôture pas le plan.")
        else:
            impot = gain * PFU
            detail.append(("Flat tax (30 %)", impot))
            notes.append("Avant 5 ans, le retrait CLÔTURE le plan et fait perdre "
                         "l'antériorité fiscale. C'est rarement le bon guichet.")

    elif modele == "av":
        if atteint:
            plafond = AV_ABATTEMENT_COUPLE if couple else AV_ABATTEMENT_SEUL
            disponible = plafond if abattement_restant is None else max(0.0, abattement_restant)
            abattu = min(gain, disponible)
            impose = gain - abattu
            impot = impose * AV_IR_REDUIT + gain * PRELEVEMENTS_SOCIAUX
            detail.append((f"Impôt sur le revenu réduit (7,5 %) sur {impose:,.0f} €".replace(",", " "),
                           impose * AV_IR_REDUIT))
            detail.append(("Prélèvements sociaux (17,2 %) sur la totalité des gains",
                           gain * PRELEVEMENTS_SOCIAUX))
            notes.append(f"{abattu:,.0f} € de gains effacés par l'abattement annuel."
                         .replace(",", " "))
            notes.append("Les prélèvements sociaux restent dus sur l'intégralité des gains : "
                         "l'abattement ne porte que sur l'impôt sur le revenu.")
        else:
            impot = gain * PFU
            detail.append(("Flat tax (30 %)", impot))
            notes.append("Avant 8 ans : pas d'abattement, et le taux réduit de 7,5 % "
                         "ne s'applique pas encore.")

    elif modele == "per":
        # Les versements déduits sont imposés au barème à la sortie, les gains
        # au PFU. Sans connaître la tranche marginale, seule la part de gains
        # est chiffrée, et le reste est signalé.
        impot = gain * PFU
        detail.append(("Flat tax sur la part de gains (30 %)", impot))
        notes.append("Le capital correspondant aux versements déduits s'ajoute à vos revenus "
                     "de l'année et suit votre tranche marginale : impôt non chiffré ici.")
        notes.append("Un PER est bloqué jusqu'à la retraite, hors cas de déblocage anticipé "
                     "(achat de la résidence principale, accidents de la vie).")

    elif modele == "metaux":
        abattement = abattement_metaux(ans)
        taux = METAUX_PLUS_VALUE * (1 - abattement)
        impot = gain * taux
        detail.append((f"Plus-values réelles ({METAUX_PLUS_VALUE:.1%}) "
                       f"après abattement de {abattement:.0%}", impot))
        notes.append("La taxe forfaitaire de 11,5 % sur le prix de vente est souvent "
                     "plus avantageuse : comparez dans le simulateur de l'enveloppe.")

    elif modele == "immobilier":
        a = abattements_immobilier(ans)
        impot = gain * (IMMO_IR * (1 - a["ir"]) + PRELEVEMENTS_SOCIAUX * (1 - a["ps"]))
        detail.append((f"Impôt sur le revenu (19 %, abattu de {a['ir']:.0%})",
                       gain * IMMO_IR * (1 - a["ir"])))
        detail.append((f"Prélèvements sociaux (17,2 %, abattus de {a['ps']:.0%})",
                       gain * PRELEVEMENTS_SOCIAUX * (1 - a["ps"])))
        notes.append("Un bien immobilier ne se vend pas par tranches : le montant retiré "
                     "suppose une cession entière.")

    elif modele == "exonere":
        impot = 0.0
        detail.append(("Exonéré", 0.0))
        notes.append("Livret réglementé : ni impôt ni prélèvements sociaux.")

    elif modele == "passif":
        impot = 0.0
        notes.append("Une dette ne se retire pas : ce compte ne peut pas financer un besoin.")

    else:   # cto, crypto et tout modèle non décrit
        impot = gain * PFU
        detail.append(("Flat tax (30 %)", impot))
        if modele == "crypto":
            notes.append(f"En deçà de {CRYPTO_SEUIL_CESSIONS} € de cessions sur l'année civile, "
                         "la plus-value est exonérée.")

    impot = max(0.0, round(impot, 2))
    return {
        "montant": round(montant, 2),
        "gain_impose": round(gain, 2),
        "impot": impot,
        "net": round(montant - impot, 2),
        "taux_effectif": round(impot / montant, 6) if montant else 0.0,
        "detail": [(libelle, round(valeur, 2)) for libelle, valeur in detail],
        "notes": notes,
        "modele": modele,
    }


def taux_marginal(compte):
    """Coût fiscal d'un euro de plus-value retiré de cette enveloppe."""
    reference = dict(compte)
    reference["valorisation"] = 1.0
    reference["pv_latent"] = 1.0
    return cout_retrait(reference, 1.0)["impot"]


# ══════════════════════════════════════════════════════════════
# ABATTEMENTS CONSOMMÉS DANS L'ANNÉE
# ══════════════════════════════════════════════════════════════
def abattements_consommes(annee=None, couple=False):
    """
    Ce qu'il reste à retirer en franchise sur l'année civile.

    Deux franchises se suivent dans le temps et non par opération : l'abattement
    annuel de l'assurance vie après 8 ans, et le seuil de cessions des
    cryptoactifs. Toutes deux se jugent sur l'année entière, ce que ni une
    position ni un mouvement pris isolément ne peut dire.

    Les rachats d'assurance vie sont chiffrés au prorata des gains **du jour**,
    faute de connaître la composition du contrat à la date du rachat : c'est
    une approximation, et elle est signalée comme telle.
    """
    annee = int(annee or datetime.date.today().year)

    from backend.accounts import list_accounts
    comptes = {c["id"]: c for c in list_accounts()}

    with get_db() as db:
        retraits = db.execute("""
            SELECT account_id, ROUND(SUM(montant_eur), 2) total, COUNT(*) nb
            FROM transactions
            WHERE type = 'retrait' AND strftime('%Y', date) = ?
            GROUP BY account_id
        """, (str(annee),)).fetchall()
        cessions = db.execute("""
            SELECT account_id, ROUND(SUM(montant_eur), 2) total, COUNT(*) nb
            FROM transactions
            WHERE type = 'vente' AND strftime('%Y', date) = ?
            GROUP BY account_id
        """, (str(annee),)).fetchall()

    # ── Assurance vie : abattement sur les gains rachetés ───────────────────
    plafond_av = AV_ABATTEMENT_COUPLE if couple else AV_ABATTEMENT_SEUL
    gains_rachetes, contrats = 0.0, []
    for ligne in retraits:
        compte = comptes.get(ligne["account_id"])
        if not compte or compte["type"] != "av":
            continue
        gain = (ligne["total"] or 0) * part_gains(compte)
        gains_rachetes += gain
        contrats.append({
            "compte": compte["nom"], "account_id": compte["id"],
            "rachete": ligne["total"], "gain_estime": round(gain, 2),
            "nb": ligne["nb"], "seuil_atteint": seuil_atteint(compte),
        })

    # ── Cryptoactifs : seuil de cessions ────────────────────────────────────
    cessions_crypto, lignes_crypto = 0.0, []
    for ligne in list(cessions) + list(retraits):
        compte = comptes.get(ligne["account_id"])
        if not compte or compte["type"] != "crypto":
            continue
        cessions_crypto += ligne["total"] or 0
        lignes_crypto.append({"compte": compte["nom"], "montant": ligne["total"], "nb": ligne["nb"]})

    return {
        "annee": annee,
        "couple": bool(couple),
        "assurance_vie": {
            "plafond": plafond_av,
            "consomme": round(min(gains_rachetes, plafond_av), 2),
            "gains_rachetes": round(gains_rachetes, 2),
            "restant": round(max(0.0, plafond_av - gains_rachetes), 2),
            "contrats": contrats,
            "estime": True,
        },
        "crypto": {
            "seuil": CRYPTO_SEUIL_CESSIONS,
            "cessions": round(cessions_crypto, 2),
            "restant": round(max(0.0, CRYPTO_SEUIL_CESSIONS - cessions_crypto), 2),
            "depasse": cessions_crypto > CRYPTO_SEUIL_CESSIONS,
            "lignes": lignes_crypto,
        },
    }


# ══════════════════════════════════════════════════════════════
# D'OÙ SORTIR UNE SOMME
# ══════════════════════════════════════════════════════════════
# Enveloppes qu'on ne pioche pas, quel que soit leur coût fiscal : un PER est
# bloqué jusqu'à la retraite, un bien immobilier ne se vend pas par tranches,
# et une dette n'est pas une réserve.
INDISPONIBLES = {"per": "bloqué jusqu'à la retraite",
                 "immobilier": "ne se vend pas par tranches",
                 "credit": "c'est une dette, pas une réserve"}


def plan_retrait(besoin, couple=False, inclure_bloquees=False):
    """
    D'où sortir `besoin` euros au moindre coût fiscal.

    Les enveloppes sont classées par **taux effectif** du retrait — l'impôt
    rapporté à la somme retirée — et non par taux marginal : une enveloppe
    lourdement taxée mais peu chargée en plus-values coûte parfois moins qu'une
    enveloppe exonérée mais entièrement composée de gains.

    L'abattement d'assurance vie se consomme au fil du plan, et non enveloppe
    par enveloppe : deux contrats rachetés la même année se partagent une seule
    franchise annuelle.
    """
    from backend.accounts import list_accounts

    besoin = max(0.0, float(besoin or 0))
    deja_consomme = abattements_consommes(couple=couple)["assurance_vie"]["consomme"]
    plafond_av = AV_ABATTEMENT_COUPLE if couple else AV_ABATTEMENT_SEUL
    abattement_restant = max(0.0, plafond_av - deja_consomme)

    candidats, ecartees = [], []
    for compte in list_accounts():
        disponible = round(compte.get("valorisation") or 0, 2)
        if disponible <= 0:
            continue
        motif = INDISPONIBLES.get(compte["type"])
        if motif and not inclure_bloquees:
            ecartees.append({"compte": compte["nom"], "type": compte["type"],
                             "valorisation": disponible, "motif": motif})
            continue
        # Le coût se juge sur le besoin entier, ou sur ce que l'enveloppe peut
        # donner : c'est le taux de ce qu'on y prendrait réellement.
        estimation = cout_retrait(compte, min(besoin, disponible) or disponible, couple,
                                  abattement_restant)
        candidats.append({
            "account_id": compte["id"], "compte": compte["nom"], "type": compte["type"],
            "type_label": compte.get("type_label", compte["type"]),
            "disponible": disponible, "part_gains": round(part_gains(compte), 6),
            "taux_effectif": estimation["taux_effectif"],
            "bloquee": bool(motif), "motif": motif,
        })

    # À coût égal, on pioche d'abord dans la plus petite enveloppe : elle sera
    # soldée plutôt que d'éparpiller le retrait sur toutes.
    candidats.sort(key=lambda c: (c["taux_effectif"], c["disponible"]))

    etapes, reste = [], besoin
    for candidat in candidats:
        if reste <= 0.01:
            break
        pris = min(reste, candidat["disponible"])
        estimation = cout_retrait(
            {"type": candidat["type"], "valorisation": candidat["disponible"],
             "pv_latent": candidat["disponible"] * candidat["part_gains"],
             "date_ouverture": _date_ouverture(candidat["account_id"])},
            pris, couple, abattement_restant)
        if candidat["type"] == "av":
            abattement_restant = max(0.0, abattement_restant - estimation["gain_impose"])
        etapes.append({**candidat, "retire": round(pris, 2), **{
            k: estimation[k] for k in ("gain_impose", "impot", "net", "detail", "notes")}})
        reste -= pris

    impot_total = round(sum(e["impot"] for e in etapes), 2)
    return {
        "besoin": round(besoin, 2),
        "couvert": round(besoin - max(0.0, reste), 2),
        "manquant": round(max(0.0, reste), 2),
        "impot_total": impot_total,
        "net_total": round(sum(e["net"] for e in etapes), 2),
        "taux_moyen": round(impot_total / (besoin - max(0.0, reste)), 6) if besoin > reste else 0.0,
        "etapes": etapes,
        "ecartees": ecartees,
        "abattement_av_restant": round(abattement_restant, 2),
    }


def _date_ouverture(account_id):
    with get_db() as db:
        ligne = db.execute("SELECT date_ouverture FROM accounts WHERE id=?",
                           (account_id,)).fetchone()
    return (ligne["date_ouverture"] if ligne else "") or ""


# ══════════════════════════════════════════════════════════════
# CESSIONS À DÉCLARER
# ══════════════════════════════════════════════════════════════
# Formulaires français, par nature d'actif cédé.
FORMULAIRES = {
    "2074": {"libelle": "Plus-values sur valeurs mobilières",
             "types": ("cto", "pea"), "colonnes": (
                 "Désignation", "Date d'acquisition", "Date de cession", "Quantité cédée",
                 "Prix de cession", "Frais de cession", "Prix de revient", "Plus-value")},
    "2086": {"libelle": "Plus-values sur actifs numériques",
             "types": ("crypto",), "colonnes": (
                 "Désignation", "Date de cession", "Prix de cession",
                 "Valeur globale du portefeuille", "Prix total d'acquisition",
                 "Fractions de capital déjà imposées", "Plus-value")},
}


def _valeur_portefeuille(db, account_id, date):
    """
    Valorisation de l'enveloppe au jour d'une cession, si elle a été relevée.

    La 2086 ne calcule pas la plus-value sur le prix de revient de la ligne
    cédée, mais au prorata de la valeur globale du portefeuille au moment de
    la cession. Sans relevé ce jour-là, la case reste à compléter à la main
    plutôt que remplie d'un chiffre inventé.
    """
    ligne = db.execute("""
        SELECT valorisation FROM history_daily
        WHERE account_id = ? AND date <= ? ORDER BY date DESC LIMIT 1
    """, (account_id, date)).fetchone()
    return round(ligne["valorisation"], 2) if ligne else None


def cessions(annee=None):
    """
    Détail cession par cession de l'année, tel que les formulaires l'attendent.

    Le journal est rejoué depuis l'origine — le prix de revient d'une vente
    dépend de tous les achats qui la précèdent — puis seules les ventes de
    l'année demandée sont retenues.

    Une ligne dont le prix de revient est incomplet est signalée : c'est le cas
    d'un relevé importé qui commence après l'acquisition, et la plus-value
    déclarée serait alors fausse.
    """
    annee = int(annee or datetime.date.today().year)

    with get_db() as db:
        groupes = db.execute("""
            SELECT t.position_id, t.nom, t.account_id, a.nom compte, a.type compte_type
            FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
            WHERE t.type IN ('achat','vente')
            GROUP BY t.position_id, t.nom, t.account_id
        """).fetchall()

        lignes = []
        for groupe in groupes:
            mouvements = db.execute("""
                SELECT type, date, quantite, prix, montant_eur, frais FROM transactions
                WHERE type IN ('achat','vente') AND account_id=?
                  AND (position_id IS ? OR (position_id IS NULL AND nom=?))
                ORDER BY date ASC, id ASC
            """, (groupe["account_id"], groupe["position_id"], groupe["nom"])).fetchall()

            quantite, cout_eur, premiere_acquisition, manquant = 0.0, 0.0, None, 0.0
            for m in mouvements:
                if m["type"] == "achat":
                    quantite += m["quantite"]
                    cout_eur += m["montant_eur"]
                    premiere_acquisition = premiere_acquisition or m["date"]
                    continue

                if quantite <= 0:
                    # Vente sans stock connu : l'acquisition précède le journal.
                    manquant += m["quantite"]
                    if m["date"][:4] == str(annee):
                        lignes.append(_cession(groupe, m, 0.0, 0.0, None, complete=False))
                    continue

                vendue = min(m["quantite"], quantite)
                part = vendue / quantite
                revient = cout_eur * part
                if m["date"][:4] == str(annee):
                    valeur_globale = (_valeur_portefeuille(db, groupe["account_id"], m["date"])
                                      if groupe["compte_type"] == "crypto" else None)
                    lignes.append(_cession(groupe, m, revient, vendue, premiere_acquisition,
                                           complete=(vendue >= m["quantite"] - 1e-9),
                                           valeur_globale=valeur_globale))
                cout_eur -= revient
                quantite -= vendue

    lignes.sort(key=lambda c: (c["formulaire"], c["date_cession"], c["designation"]))
    par_formulaire = {}
    for ligne in lignes:
        par_formulaire.setdefault(ligne["formulaire"], []).append(ligne)

    return {
        "annee": annee,
        "formulaires": [{
            "code": code, **FORMULAIRES[code],
            "lignes": par_formulaire.get(code, []),
            "total_cession": round(sum(l["prix_cession"] for l in par_formulaire.get(code, [])), 2),
            # Les cessions incomplètes entrent dans le total cédé — la vente a
            # bien eu lieu — mais pas dans la plus-value, qu'on ignore.
            "total_plus_value": round(sum(l["plus_value"] for l in par_formulaire.get(code, [])
                                          if l["plus_value"] is not None), 2),
            "incompletes": sum(1 for l in par_formulaire.get(code, []) if not l["complete"]),
        } for code in FORMULAIRES if par_formulaire.get(code)],
        "hors_formulaire": par_formulaire.get("", []),
    }


def _formulaire(compte_type):
    for code, forme in FORMULAIRES.items():
        if compte_type in forme["types"]:
            return code
    return ""


def _cession(groupe, mouvement, revient, quantite, premiere_acquisition,
             complete=True, valeur_globale=None):
    prix_cession = round(mouvement["montant_eur"], 2)
    return {
        "formulaire": _formulaire(groupe["compte_type"]),
        "designation": groupe["nom"],
        "compte": groupe["compte"],
        "compte_type": groupe["compte_type"],
        "date_acquisition": premiere_acquisition or "",
        "date_cession": mouvement["date"],
        "quantite": round(quantite or mouvement["quantite"], 6),
        "prix_cession": prix_cession,
        "frais": round(mouvement["frais"] or 0, 2),
        "prix_revient": round(revient, 2),
        "valeur_portefeuille": valeur_globale,
        # Sans prix de revient, la plus-value n'est pas nulle : elle est
        # inconnue. Afficher zéro la ferait disparaître d'une déclaration,
        # afficher le prix de cession entier la gonflerait.
        "plus_value": round(prix_cession - revient, 2) if complete else None,
        "complete": complete,
    }
