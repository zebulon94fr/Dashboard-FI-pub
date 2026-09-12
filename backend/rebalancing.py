"""Rééquilibrage par classe d'actifs.

Trois changements par rapport au rééquilibrage par enveloppe :

  * **l'axe**. Une enveloppe n'est pas une classe d'actifs — un PEA peut être
    investi à 100 % en actions comme dormir en liquidités. Piloter « PEA 40 %,
    assurance vie 30 % » revient à piloter une allocation fiscale en croyant
    piloter une allocation d'actifs ;
  * **les bandes**. Un seuil unique en points traite de la même façon une cible
    à 5 % et une cible à 60 %. La bande est relative à la cible, avec un
    plancher en points pour que les petites lignes ne déclenchent pas à tout va ;
  * **l'ordre de résolution**. L'apport neuf est dirigé en premier vers les
    classes sous-pondérées ; les ventes ne viennent qu'après, et sont proposées
    en commençant par les moins-values — qui s'imputent sur les plus-values de
    l'année — puis par les plus faibles plus-values. L'ordre inverse, qui
    consistait à alléger les plus grosses plus-values, maximisait l'impôt.
"""
from backend.db import get_db
from catalog import CLASSES_ACTIFS, ORDRE_CLASSES, PFU

# Taux d'imposition d'un *arbitrage* interne, enveloppe par enveloppe. Dans une
# enveloppe capitalisante, réallouer entre supports ne déclenche aucune
# imposition — seul le retrait en est le fait générateur.
TAUX_ARBITRAGE = {
    "pea": 0.0, "av": 0.0, "per": 0.0,
    "cto": PFU, "crypto": PFU, "metaux": 0.362,
}

# Règle « 5/25 » : une classe dérive dès qu'elle s'écarte de 5 points de sa
# cible **ou** de 25 % de celle-ci — soit une bande égale au plus petit des
# deux. Prendre le plus grand donnerait 17,5 points de tolérance à une cible de
# 70 %, ce qui ne déclencherait jamais. Un plancher d'un point évite qu'une
# cible marginale ne se déclenche au moindre bruit de marché.
BANDE_RELATIVE = 0.25
BANDE_PLAFOND_PTS = 5.0
BANDE_PLANCHER_PTS = 1.0
# En deçà, l'arbitrage coûte plus en frais qu'il ne rapporte en alignement.
ORDRE_MINIMUM_EUR = 100.0

# Contrainte fiscale propre à chaque enveloppe, rappelée avant toute vente.
AVERTISSEMENTS = {
    "pea": "Sur un PEA, arbitrez en interne : un retrait avant 5 ans clôture le plan.",
    "av": "Sur une assurance vie, un arbitrage entre supports n'est pas imposable — un rachat l'est.",
    "per": "Un PER est bloqué jusqu'à la retraite : rééquilibrez par arbitrage interne.",
    "cto": "Sur un compte-titres, chaque plus-value réalisée est taxée à 30 %.",
    "crypto": "Une conversion en euros déclenche l'imposition ; un échange entre cryptoactifs, non.",
    "metaux": "La revente de métaux est taxée dès le premier euro : vérifiez la durée de détention.",
}


def save_cibles_classes(cibles):
    """Enregistre l'allocation cible par classe : {classe: pourcentage}."""
    with get_db() as db:
        for classe, pct in (cibles or {}).items():
            if classe not in CLASSES_ACTIFS:
                continue
            try:
                valeur = min(100.0, max(0.0, float(pct)))
            except (TypeError, ValueError):
                continue
            db.execute("""
                INSERT INTO allocations_classes (classe, cible_pct) VALUES (?,?)
                ON CONFLICT(classe) DO UPDATE SET cible_pct=excluded.cible_pct
            """, (classe, valeur))


def _cout_fiscal(compte_type, pv_latent):
    """
    Impôt estimé si l'on réalisait la plus-value de cette ligne aujourd'hui.

    Dans une enveloppe capitalisante, un arbitrage entre supports ne déclenche
    rien : seul un retrait est imposable. Alléger une ligne y coûte donc zéro,
    ce qu'un tri fondé sur la seule plus-value ne peut pas voir.
    """
    if pv_latent <= 0:
        return 0.0
    taux = TAUX_ARBITRAGE.get(compte_type, PFU)
    return pv_latent * taux


def _candidats_vente(positions, classe):
    """
    Lignes d'une classe, dans l'ordre où les alléger coûte le moins d'impôt.

    Les moins-values viennent d'abord — elles s'imputent sur les plus-values de
    l'année —, puis les lignes logées dans une enveloppe où l'arbitrage est
    neutre, puis les plus faibles plus-values imposables.
    """
    lignes = [p for p in positions
              if (p["classe"] or "autre") == classe and (p["valorisation"] or 0) > 0]
    lignes.sort(key=lambda p: (_cout_fiscal(p["compte_type"], p["pv_latent"] or 0),
                               p["pv_latent"] or 0))
    return lignes


def get_rebalancing(apport=0.0, bande_relative=BANDE_RELATIVE,
                    plafond_pts=BANDE_PLAFOND_PTS, plancher_pts=BANDE_PLANCHER_PTS,
                    ordre_minimum=ORDRE_MINIMUM_EUR):
    """Écarts par classe, puis mouvements recommandés apport en tête."""
    with get_db() as db:
        positions = db.execute("""
            SELECT p.id, p.nom, COALESCE(NULLIF(p.classe, ''), 'autre') classe,
                   p.valorisation, p.pv_latent, p.pv_pct,
                   a.nom compte, a.type compte_type
            FROM positions p JOIN accounts a ON a.id = p.account_id
            WHERE p.valorisation > 0
        """).fetchall()
        cibles = {r["classe"]: r["cible_pct"]
                  for r in db.execute("SELECT classe, cible_pct FROM allocations_classes")}

    total = sum(p["valorisation"] for p in positions)
    apport = max(0.0, float(apport or 0))
    total_cible = total + apport
    total_cibles = sum(cibles.values())

    reelles = {}
    for p in positions:
        reelles[p["classe"]] = reelles.get(p["classe"], 0.0) + p["valorisation"]

    classes = []
    for classe in ORDRE_CLASSES:
        valorisation = reelles.get(classe, 0.0)
        cible = cibles.get(classe, 0.0)
        if not valorisation and not cible:
            continue

        poids = (valorisation / total * 100) if total else 0.0
        ecart_pts = cible - poids
        bande = max(min(cible * bande_relative, plafond_pts), plancher_pts)
        montant_cible = total_cible * cible / 100
        ecart_eur = montant_cible - valorisation

        classes.append({
            "classe": classe,
            "label": CLASSES_ACTIFS[classe]["label"],
            "couleur": CLASSES_ACTIFS[classe]["couleur"],
            "valorisation": round(valorisation, 2),
            "poids": round(poids, 2),
            "cible_pct": cible,
            "montant_cible": round(montant_cible, 2),
            "ecart_pts": round(ecart_pts, 2),
            "ecart_eur": round(ecart_eur, 2),
            "bande": round(bande, 2),
            "hors_bande": abs(ecart_pts) > bande,
            "statut": ("equilibre" if abs(ecart_pts) <= bande
                       else "sous_pondere" if ecart_pts > 0 else "sur_pondere"),
        })

    # ── Résolution : l'apport d'abord, les ventes seulement ensuite ──────────
    sous_ponderees = sorted(
        [c for c in classes if c["statut"] == "sous_pondere"],
        key=lambda c: c["ecart_eur"], reverse=True)
    sur_ponderees = sorted(
        [c for c in classes if c["statut"] == "sur_pondere"],
        key=lambda c: c["ecart_eur"])

    besoin_total = sum(c["ecart_eur"] for c in sous_ponderees)
    apports, restant = [], apport

    for c in sous_ponderees:
        part = min(c["ecart_eur"], restant) if restant > 0 else 0.0
        restant -= part
        apports.append({
            **{k: c[k] for k in ("classe", "label", "couleur", "poids", "cible_pct",
                                 "valorisation", "montant_cible", "ecart_eur")},
            "apport_affecte": round(part, 2),
            "reste_a_financer": round(c["ecart_eur"] - part, 2),
        })

    # Une vente n'est proposée que pour ce que l'apport ne couvre pas.
    a_financer = max(0.0, besoin_total - apport)
    ventes = []
    for c in sur_ponderees:
        if a_financer <= 0:
            break
        montant = min(abs(c["ecart_eur"]), a_financer)
        if montant < ordre_minimum:
            continue
        a_financer -= montant

        candidats = _candidats_vente(positions, c["classe"])[:3]
        ventes.append({
            **{k: c[k] for k in ("classe", "label", "couleur", "poids", "cible_pct",
                                 "valorisation", "montant_cible")},
            "montant": round(montant, 2),
            "lignes": [{
                "nom": p["nom"], "compte": p["compte"], "compte_type": p["compte_type"],
                "valorisation": round(p["valorisation"], 2),
                "pv_latent": round(p["pv_latent"] or 0, 2),
                "pv_pct": round(p["pv_pct"] or 0, 6),
                "cout_fiscal": round(_cout_fiscal(p["compte_type"], p["pv_latent"] or 0), 2),
                "avertissement": AVERTISSEMENTS.get(p["compte_type"], ""),
            } for p in candidats],
        })

    hors_bande = [c for c in classes if c["hors_bande"]]
    return {
        "total": round(total, 2),
        "apport": round(apport, 2),
        "total_cible": round(total_cible, 2),
        "total_cibles": round(total_cibles, 2),
        "cibles_valides": abs(total_cibles - 100) <= 0.01,
        "classes": classes,
        "apports": apports,
        "ventes": ventes,
        "resume": {
            "nb_hors_bande": len(hors_bande),
            "besoin_total": round(besoin_total, 2),
            "apport_utilise": round(min(apport, besoin_total), 2),
            "apport_non_affecte": round(max(0.0, apport - besoin_total), 2),
            "a_vendre": round(sum(v["montant"] for v in ventes), 2),
            "reste_a_financer": round(a_financer, 2),
            "derive_max": round(max((abs(c["ecart_pts"]) for c in classes), default=0), 2),
            "ordre_minimum": ordre_minimum,
        },
        "parametres": {
            "bande_relative": bande_relative,
            "plafond_pts": plafond_pts,
            "plancher_pts": plancher_pts,
            "ordre_minimum": ordre_minimum,
        },
        "non_classees": sum(1 for p in positions if p["classe"] == "autre"),
    }
