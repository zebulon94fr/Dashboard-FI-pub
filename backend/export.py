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
