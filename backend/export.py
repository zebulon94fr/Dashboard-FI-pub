"""Génération du CSV d'export du portefeuille."""
from catalog import ACCOUNT_TYPES


def generate_csv(portfolio):
    comptes = portfolio.get("accounts", [])

    lignes = ["Compte;Type;Établissement;Position;Ticker;ISIN;Quantité;PRU;Devise;"
              "Cours;Taux de change;Valorisation (EUR);+/- Latent (EUR);+/- %"]
    for compte in comptes:
        type_label = ACCOUNT_TYPES.get(compte["type"], {}).get("label", compte["type"])
        for p in compte.get("positions", []):
            lignes.append(";".join([
                compte["nom"],
                type_label,
                compte.get("etablissement", ""),
                p.get("nom", ""),
                p.get("ticker", ""),
                p.get("isin", ""),
                f"{p.get('quantite', 0):.6f}",
                f"{p.get('pru', 0):.4f}",
                p.get("devise", "EUR"),
                f"{p.get('cours', 0):.4f}",
                f"{p.get('taux_change', 1):.6f}",
                f"{p.get('valorisation', 0):.2f}",
                f"{p.get('pv_latent', 0):.2f}",
                f"{p.get('pv_pct', 0):.2%}",
            ]))

    lignes += ["", "=== TOTAUX PAR COMPTE ===",
               "Compte;Type;Valorisation (EUR);Investi (EUR);+/- Latent (EUR);+/- %"]
    for compte in comptes:
        type_label = ACCOUNT_TYPES.get(compte["type"], {}).get("label", compte["type"])
        lignes.append(";".join([
            compte["nom"], type_label,
            f"{compte.get('valorisation', 0):.2f}",
            f"{compte.get('investi', 0):.2f}",
            f"{compte.get('pv_latent', 0):.2f}",
            f"{compte.get('pv_pct', 0):.2%}",
        ]))

    historique = portfolio.get("history", [])
    if historique:
        entetes = ["Date"] + [c["nom"] for c in comptes] + ["Total"]
        lignes += ["", "=== HISTORIQUE JOURNALIER ===", ";".join(entetes)]
        for jour in historique:
            valeurs = [f"{jour['comptes'].get(str(c['id']), 0):.2f}" for c in comptes]
            lignes.append(";".join([jour["date"]] + valeurs + [f"{jour.get('total', 0):.2f}"]))

    return "\n".join(lignes)


def generate_csv_cessions(detail):
    """
    Cessions de l'année, groupées par formulaire, prêtes à reporter.

    Un seul fichier plutôt qu'un par formulaire : on remplit sa déclaration
    d'une traite, et séparer obligerait à jongler entre deux téléchargements.
    Les colonnes suivent celles du formulaire, dans son ordre.
    """
    lignes = [f"Cessions de l'année {detail['annee']}", ""]

    for forme in detail["formulaires"]:
        lignes.append(f"=== FORMULAIRE {forme['code']} — {forme['libelle'].upper()} ===")
        lignes.append(";".join(forme["colonnes"]))
        for c in forme["lignes"]:
            if forme["code"] == "2086":
                valeurs = [
                    c["designation"], c["date_cession"], f"{c['prix_cession']:.2f}",
                    f"{c['valeur_portefeuille']:.2f}" if c["valeur_portefeuille"] else "à compléter",
                    f"{c['prix_revient']:.2f}", "0.00", f"{c['plus_value']:.2f}",
                ]
            else:
                valeurs = [
                    c["designation"], c["date_acquisition"] or "à compléter", c["date_cession"],
                    f"{c['quantite']:g}", f"{c['prix_cession']:.2f}", f"{c['frais']:.2f}",
                    f"{c['prix_revient']:.2f}" if c["complete"] else "à compléter",
                    f"{c['plus_value']:.2f}" if c["complete"] else "à compléter",
                ]
            lignes.append(";".join(valeurs))

        # Les totaux se placent sous leur propre colonne : les deux formulaires
        # n'ont ni la même largeur ni le même ordre, et un découpage positionnel
        # ferait tomber la plus-value du 2086 hors du tableau.
        total = ["" for _ in forme["colonnes"]]
        total[0] = "TOTAL"
        for intitule, valeur in (("Prix de cession", forme["total_cession"]),
                                 ("Plus-value", forme["total_plus_value"])):
            if intitule in forme["colonnes"]:
                total[forme["colonnes"].index(intitule)] = f"{valeur:.2f}"
        lignes.append(";".join(total))
        if forme["incompletes"]:
            lignes.append(f"ATTENTION : {forme['incompletes']} cession(s) sans prix de revient "
                          "connu — leur plus-value est à établir avant déclaration.")
        lignes.append("")

    lignes.append("Estimations reconstituées depuis le journal des mouvements, "
                  "au prix moyen pondéré. À vérifier avant toute déclaration.")
    return "\n".join(lignes)
