"""Données de référence, communes à tous les utilisateurs.

Rien ici n'est propre à un portefeuille : ce sont les enveloppes fiscales
françaises, leurs règles d'imposition, et des catalogues de tickers Yahoo
Finance réutilisables. Les comptes et les positions, eux, sont créés par
l'utilisateur et vivent en base (voir backend/accounts.py).
"""

# ── Taux d'imposition (France, en vigueur au 1er janvier 2026) ──────────────
PRELEVEMENTS_SOCIAUX = 0.172   # CSG/CRDS et assimilés
PFU_IR               = 0.128   # part impôt sur le revenu du prélèvement forfaitaire unique
PFU                  = PRELEVEMENTS_SOCIAUX + PFU_IR   # « flat tax » : 30 %

# ── Types de comptes proposés à la création ─────────────────────────────────
# `modele_fiscal` désigne le simulateur utilisé par l'onglet Fiscalité ;
# `seuil_ans` la durée de détention qui déclenche l'avantage fiscal (le cas
# échéant), calculée à partir de la date d'ouverture saisie sur le compte.
ACCOUNT_TYPES = {
    "pea": {
        "label": "PEA",
        "nom_complet": "Plan d'Épargne en Actions",
        "icone": "📈",
        "couleur": "#58a6ff",
        "unite": "titres",
        "decimales": 4,
        "devise_defaut": "EUR",
        "exemple_nom": "PEA",
        "exemple_etablissement": "Bourse Direct, Fortuneo, Boursorama…",
        "seuil_ans": 5,
        "plafond": 150000,
        "modele_fiscal": "pea",
        "resume_fiscal": (
            "Après 5 ans de détention, les plus-values et dividendes sont exonérés "
            "d'impôt sur le revenu : seuls les prélèvements sociaux de 17,2 % "
            "s'appliquent sur les gains lors d'un retrait. Avant 5 ans, le retrait "
            "est soumis à la flat tax de 30 % et entraîne la clôture du plan."
        ),
        "regles": [
            ["Impôt sur le revenu (après 5 ans)", "0 % — exonéré", "pos"],
            ["Prélèvements sociaux", "17,2 %", ""],
            ["Retrait avant 5 ans", "30 % (PFU) + clôture", "neg"],
            ["Retrait partiel après 5 ans", "Oui, sans clôture", "pos"],
            ["Plafond de versements", "150 000 €", ""],
            ["Univers éligible", "Actions et fonds européens", ""],
        ],
    },
    "cto": {
        "label": "CTO",
        "nom_complet": "Compte-Titres Ordinaire",
        "icone": "🌍",
        "couleur": "#bc8cff",
        "unite": "titres",
        "decimales": 4,
        "devise_defaut": "EUR",
        "exemple_nom": "CTO",
        "exemple_etablissement": "Saxo, Interactive Brokers, Trade Republic…",
        "seuil_ans": None,
        "plafond": None,
        "modele_fiscal": "flat",
        "resume_fiscal": (
            "Le compte-titres n'offre aucune exonération liée à la durée de "
            "détention : chaque plus-value réalisée est taxée dès la vente à la "
            "flat tax de 30 % (12,8 % d'IR + 17,2 % de prélèvements sociaux), "
            "sauf option globale pour le barème progressif si elle est plus favorable."
        ),
        "regles": [
            ["Impôt sur le revenu (PFU)", "12,8 %", "neg"],
            ["Prélèvements sociaux", "17,2 %", "neg"],
            ["Total flat tax", "30 %", "neg"],
            ["Option barème progressif", "Possible si TMI faible", ""],
            ["Exonération liée à la durée", "Aucune", "neg"],
            ["Plafond de versements", "Aucun", "pos"],
            ["Univers éligible", "Tous marchés, toutes devises", "pos"],
        ],
    },
    "per": {
        "label": "PER",
        "nom_complet": "Plan d'Épargne Retraite",
        "icone": "🧓",
        "couleur": "#f0883e",
        "unite": "parts",
        "decimales": 4,
        "devise_defaut": "EUR",
        "exemple_nom": "PER individuel",
        "exemple_etablissement": "Assureur ou gestionnaire",
        "seuil_ans": None,
        "plafond": None,
        "modele_fiscal": "per",
        "resume_fiscal": (
            "Les versements volontaires sont déductibles du revenu imposable dans "
            "la limite du plafond épargne retraite : l'économie d'impôt immédiate "
            "dépend de la tranche marginale (TMI). En contrepartie, l'épargne est "
            "bloquée jusqu'à la retraite (hors cas de déblocage anticipé) et la "
            "sortie en capital est imposée : barème de l'IR sur les versements "
            "déduits, flat tax de 30 % sur les gains."
        ),
        "regles": [
            ["Versements volontaires", "Déductibles du revenu imposable", "pos"],
            ["Sortie en capital — versements déduits", "Barème de l'IR", "neg"],
            ["Sortie en capital — gains", "30 % (PFU)", "neg"],
            ["Sortie en rente", "Barème de l'IR (régime RVTG)", ""],
            ["Disponibilité", "Bloqué jusqu'à la retraite", "neg"],
            ["Déblocage anticipé", "Résidence principale, accidents de la vie", ""],
        ],
    },
    "av": {
        "label": "Assurance Vie",
        "nom_complet": "Contrat d'assurance vie",
        "icone": "🛡️",
        "couleur": "#3fb950",
        "unite": "parts",
        "decimales": 4,
        "devise_defaut": "EUR",
        "exemple_nom": "Assurance vie",
        "exemple_etablissement": "Assureur ou courtier",
        "seuil_ans": 8,
        "plafond": None,
        "modele_fiscal": "av",
        "resume_fiscal": (
            "Après 8 ans, les gains rachetés bénéficient d'un abattement annuel de "
            "4 600 € (9 200 € pour un couple soumis à imposition commune), puis "
            "d'un taux d'IR réduit à 7,5 % tant que les versements cumulés restent "
            "sous 150 000 €. Les prélèvements sociaux de 17,2 % s'appliquent dans "
            "tous les cas. Avant 8 ans, les gains rachetés subissent la flat tax de 30 %."
        ),
        "regles": [
            ["Abattement annuel après 8 ans", "4 600 € (9 200 € en couple)", "pos"],
            ["IR après 8 ans, au-delà de l'abattement", "7,5 % (versements < 150 k€)", "pos"],
            ["IR avant 8 ans", "12,8 % (PFU)", "neg"],
            ["Prélèvements sociaux", "17,2 % (toujours)", ""],
            ["Rachat partiel", "Possible à tout moment", "pos"],
            ["Transmission", "Abattement de 152 500 € par bénéficiaire", "pos"],
        ],
    },
    "metaux": {
        "label": "Métaux précieux",
        "nom_complet": "Or, argent et métaux d'investissement",
        "icone": "🥇",
        "couleur": "#f5c518",
        "unite": "oz",
        "decimales": 4,
        "devise_defaut": "USD",
        "exemple_nom": "Métaux précieux",
        "exemple_etablissement": "Coffre, banque, opérateur spécialisé…",
        "seuil_ans": 22,
        "plafond": None,
        "modele_fiscal": "metaux",
        "resume_fiscal": (
            "Deux régimes au choix lors de la revente : la taxe forfaitaire de "
            "11,5 % assise sur le prix de cession (sans justificatif d'achat), ou "
            "le régime des plus-values réelles à 36,2 % avec un abattement de 5 % "
            "par an de détention au-delà de la deuxième année — soit une "
            "exonération totale après 22 ans."
        ),
        "regles": [
            ["Taxe forfaitaire sur le prix de cession", "11,5 %", ""],
            ["Régime des plus-values réelles", "36,2 % (19 % IR + 17,2 % PS)", "neg"],
            ["Abattement pour durée de détention", "5 %/an au-delà de la 2ᵉ année", "pos"],
            ["Exonération totale", "Après 22 ans de détention", "pos"],
            ["Justificatif d'achat", "Requis pour le régime des plus-values", ""],
            ["Détention physique", "Hors circuit bancaire possible", ""],
        ],
    },
    "crypto": {
        "label": "Cryptomonnaies",
        "nom_complet": "Actifs numériques",
        "icone": "₿",
        "couleur": "#2dd4bf",   # turquoise : se distingue du vert de l'assurance vie
        "unite": "unités",
        "decimales": 8,
        "devise_defaut": "EUR",
        "exemple_nom": "Cryptomonnaies",
        "exemple_etablissement": "Plateforme d'échange ou wallet",
        "seuil_ans": None,
        "plafond": None,
        "modele_fiscal": "crypto",
        "resume_fiscal": (
            "Les plus-values de cession d'actifs numériques par un particulier "
            "sont imposées à la flat tax de 30 %, avec option possible pour le "
            "barème progressif. Les cessions sont exonérées tant que leur total "
            "annuel reste sous 305 €. Les échanges crypto contre crypto ne "
            "déclenchent pas d'imposition : seule la conversion en monnaie ayant "
            "cours légal est un fait générateur."
        ),
        "regles": [
            ["Impôt sur le revenu (PFU)", "12,8 %", "neg"],
            ["Prélèvements sociaux", "17,2 %", "neg"],
            ["Total flat tax", "30 %", "neg"],
            ["Option barème progressif", "Possible depuis 2023", ""],
            ["Exonération", "Cessions annuelles < 305 €", "pos"],
            ["Échange crypto ↔ crypto", "Non imposable", "pos"],
            ["Comptes détenus à l'étranger", "À déclarer (formulaire 3916-bis)", ""],
        ],
    },
}

ORDRE_TYPES = ["pea", "cto", "per", "av", "metaux", "crypto"]

# ── Catalogues de tickers Yahoo Finance ─────────────────────────────────────
# Proposés en autocomplétion à la saisie d'une position ; l'utilisateur reste
# libre de saisir n'importe quel autre ticker.
CRYPTO_CATALOG = [
    ("Bitcoin", "BTC-EUR", "EUR"),
    ("Ethereum", "ETH-EUR", "EUR"),
    ("BNB", "BNB-EUR", "EUR"),
    ("Solana", "SOL-EUR", "EUR"),
    ("XRP", "XRP-EUR", "EUR"),
    ("Cardano", "ADA-EUR", "EUR"),
    ("Avalanche", "AVAX-EUR", "EUR"),
    ("Polkadot", "DOT-EUR", "EUR"),
    ("Chainlink", "LINK-EUR", "EUR"),
    ("Litecoin", "LTC-EUR", "EUR"),
    ("Dogecoin", "DOGE-EUR", "EUR"),
    ("Uniswap", "UNI-EUR", "EUR"),
    ("Cosmos", "ATOM-EUR", "EUR"),
    ("Tether", "USDT-EUR", "EUR"),
    ("USD Coin", "USDC-EUR", "EUR"),
]

METAL_CATALOG = [
    ("Or (once)", "GC=F", "USD"),
    ("Argent (once)", "SI=F", "USD"),
    ("Platine (once)", "PL=F", "USD"),
    ("Palladium (once)", "PA=F", "USD"),
    ("Cuivre (livre)", "HG=F", "USD"),
]

# Devises proposées dans le formulaire de position.
DEVISES = ["EUR", "USD", "GBP", "CHF", "CAD", "JPY", "HKD", "AUD", "SEK", "NOK", "DKK", "SGD"]

# Indices de comparaison de l'onglet Historique.
BENCHMARK_TICKERS = {
    "CAC 40":     "^FCHI",
    "MSCI World": "URTH",
    "S&P 500":    "^GSPC",
    "Nasdaq 100": "^NDX",
    "MSCI Europe": "IMEU.L",
}


def fx_ticker(devise):
    """Ticker Yahoo du taux EUR -> `devise` (l'inverse de ce qu'on cherche)."""
    return f"EUR{devise}=X"


def type_info(type_id):
    return ACCOUNT_TYPES.get(type_id, {})


def public_types():
    """Catalogue sérialisable envoyé au frontend (GET /api/account-types)."""
    out = []
    for tid in ORDRE_TYPES:
        t = dict(ACCOUNT_TYPES[tid])
        t["id"] = tid
        if tid == "crypto":
            t["suggestions"] = [{"nom": n, "ticker": tk, "devise": d} for n, tk, d in CRYPTO_CATALOG]
        elif tid == "metaux":
            t["suggestions"] = [{"nom": n, "ticker": tk, "devise": d} for n, tk, d in METAL_CATALOG]
        else:
            t["suggestions"] = []
        out.append(t)
    return out
