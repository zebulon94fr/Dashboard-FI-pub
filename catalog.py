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
        "exemple_etablissement": "Banque ou courtier en ligne",
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
        "exemple_etablissement": "Courtier français ou international",
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
    "liquidites": {
        "label": "Liquidités",
        "nom_complet": "Livrets et comptes courants",
        "icone": "💧",
        "couleur": "#79c0ff",
        "unite": "€",
        "decimales": 2,
        "devise_defaut": "EUR",
        "exemple_nom": "Livret A",
        "exemple_etablissement": "Banque",
        "seuil_ans": None,
        "plafond": None,
        "modele_fiscal": "exonere",
        "resume_fiscal": (
            "Les livrets réglementés — Livret A, LDDS, LEP — sont exonérés d'impôt "
            "sur le revenu comme de prélèvements sociaux. Un compte courant ne "
            "produit pas d'intérêts. Un livret bancaire ordinaire, en revanche, est "
            "soumis à la flat tax de 30 % sur les intérêts versés."
        ),
        "regles": [
            ["Livrets réglementés", "Exonérés d'IR et de PS", "pos"],
            ["Livret bancaire ordinaire", "30 % sur les intérêts", "neg"],
            ["Disponibilité", "Immédiate", "pos"],
            ["Rôle", "Épargne de précaution", ""],
            ["Plafond Livret A", "22 950 €", ""],
            ["Plafond LDDS", "12 000 €", ""],
        ],
    },
    "immobilier": {
        "label": "Immobilier",
        "nom_complet": "Biens immobiliers et parts de SCPI",
        "icone": "🏠",
        "couleur": "#d29922",
        "unite": "parts",
        "decimales": 4,
        "devise_defaut": "EUR",
        "exemple_nom": "Résidence principale",
        "exemple_etablissement": "Bien détenu en direct, SCPI…",
        "seuil_ans": 30,
        "plafond": None,
        "modele_fiscal": "immobilier",
        "resume_fiscal": (
            "La plus-value de cession de la résidence principale est totalement "
            "exonérée. Pour les autres biens, elle est taxée à 19 % d'impôt sur le "
            "revenu et 17,2 % de prélèvements sociaux, avec des abattements pour "
            "durée de détention différents pour chacun : exonération d'IR après "
            "22 ans, de prélèvements sociaux après 30 ans."
        ),
        "regles": [
            ["Résidence principale", "Plus-value exonérée", "pos"],
            ["Autres biens — impôt sur le revenu", "19 %", "neg"],
            ["Autres biens — prélèvements sociaux", "17,2 %", "neg"],
            ["Exonération d'IR", "Après 22 ans de détention", "pos"],
            ["Exonération de prélèvements sociaux", "Après 30 ans", "pos"],
            ["Revenus locatifs", "Barème de l'IR ou micro-foncier", ""],
        ],
    },
    "credit": {
        "label": "Crédit",
        "nom_complet": "Emprunt en cours — passif",
        "icone": "🏦",
        "couleur": "#f85149",
        "unite": "€",
        "decimales": 2,
        "devise_defaut": "EUR",
        "exemple_nom": "Crédit immobilier",
        "exemple_etablissement": "Banque prêteuse",
        "seuil_ans": None,
        "plafond": None,
        "passif": True,
        "modele_fiscal": "passif",
        "resume_fiscal": (
            "Un crédit se déduit du patrimoine : saisissez le capital restant dû "
            "comme valorisation, et mettez-le à jour au fil des remboursements. "
            "C'est ce qui sépare le patrimoine brut du patrimoine net — pour un "
            "ménage qui rembourse sa résidence principale, l'écart est souvent "
            "l'essentiel du bilan."
        ),
        "regles": [
            ["Effet sur le patrimoine", "Déduit du patrimoine brut", "neg"],
            ["Valorisation à saisir", "Capital restant dû", ""],
            ["Intérêts d'emprunt", "Déductibles des revenus fonciers", ""],
            ["Assurance emprunteur", "À compter dans le coût total", ""],
        ],
    },
}

ORDRE_TYPES = ["pea", "cto", "per", "av", "metaux", "crypto", "liquidites", "immobilier", "credit"]

# Types dont la valorisation se retranche du patrimoine au lieu de s'y ajouter.
TYPES_PASSIF = {tid for tid, t in ACCOUNT_TYPES.items() if t.get("passif")}

# ── Types de mouvement du journal ───────────────────────────────────────────
# `sens` est le signe du flux du point de vue du portefeuille : +1 quand de
# l'argent y entre, -1 quand il en sort. C'est ce signe qui neutralise les
# apports dans le TWR et qui date les flux du TRI (voir backend/performance.py).
# `ligne` indique si le mouvement porte sur une position précise (achat, vente)
# ou sur l'enveloppe entière (versement, retrait, frais).
TYPES_TRANSACTION = {
    "achat":     {"label": "Achat",     "icone": "🟢", "sens": 1,  "ligne": True},
    "vente":     {"label": "Vente",     "icone": "🔴", "sens": -1, "ligne": True},
    "versement": {"label": "Versement", "icone": "⬇",  "sens": 1,  "ligne": False},
    "retrait":   {"label": "Retrait",   "icone": "⬆",  "sens": -1, "ligne": False},
    "frais":     {"label": "Frais",     "icone": "✂",  "sens": -1, "ligne": False},
}

ORDRE_TRANSACTIONS = ["achat", "vente", "versement", "retrait", "frais"]

# ── Classes d'actifs ────────────────────────────────────────────────────────
# Une enveloppe n'est pas une classe d'actifs : un PEA peut être investi à 100 %
# en actions comme dormir en liquidités. L'allocation cible se pilote donc sur
# cet axe, toutes enveloppes confondues, et la répartition par enveloppe reste
# une vue secondaire — utile, mais fiscale plutôt qu'allocataire.
# Les teintes reprennent celles que l'application emploie déjà pour les mêmes
# actifs (métaux en or, cryptoactifs en turquoise), pour que le graphique des
# classes et celui des enveloppes ne se contredisent pas. Seul « Non classé »
# reste neutre : c'est la catégorie vide, comme « Non renseigné » ailleurs.
CLASSES_ACTIFS = {
    "actions":    {"label": "Actions",        "couleur": "#58a6ff", "volatilite": 0.17},
    "obligations": {"label": "Obligations",   "couleur": "#3fb950", "volatilite": 0.06},
    "monetaire":  {"label": "Monétaire",      "couleur": "#bc8cff", "volatilite": 0.01},
    "immobilier": {"label": "Immobilier",     "couleur": "#f0883e", "volatilite": 0.12},
    "or":         {"label": "Or et métaux",   "couleur": "#f5c518", "volatilite": 0.15},
    "crypto":     {"label": "Cryptoactifs",   "couleur": "#2dd4bf", "volatilite": 0.60},
    "autre":      {"label": "Non classé",     "couleur": "#6e7681", "volatilite": 0.15},
}

ORDRE_CLASSES = ["actions", "obligations", "monetaire", "immobilier", "or", "crypto", "autre"]

# Classe proposée par défaut selon le type d'enveloppe, à la création d'une
# position. Un simple point de départ : l'utilisateur reste libre de la changer.
CLASSE_PAR_DEFAUT = {
    "pea": "actions", "cto": "actions", "per": "actions",
    "av": "obligations", "metaux": "or", "crypto": "crypto",
    "liquidites": "monetaire", "immobilier": "immobilier",
}

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
#
# `devise` est indispensable : un indice coté en dollars comparé tel quel à un
# portefeuille en euros se trompe exactement de la variation EUR/USD de la
# période. Chaque série est donc reconvertie en euros avant comparaison.
#
# `rendement` distingue un indice **prix** (dividendes exclus) d'une série à
# **rendement total**. Se comparer à un indice prix revient à s'offrir les
# dividendes gratuitement : c'est signalé à l'écran. Pour passer un indice en
# rendement total, remplacer son ticker par celui d'un ETF capitalisant coté en
# euros — rien d'autre à changer ici.
BENCHMARK_TICKERS = {
    "CAC 40":            {"ticker": "^FCHI",  "devise": "EUR", "rendement": "prix"},
    "S&P 500":           {"ticker": "^GSPC",  "devise": "USD", "rendement": "prix"},
    "Nasdaq 100":        {"ticker": "^NDX",   "devise": "USD", "rendement": "prix"},
    "MSCI World":        {"ticker": "URTH",   "devise": "USD", "rendement": "total"},
    "STOXX Europe 600":  {"ticker": "^STOXX", "devise": "EUR", "rendement": "prix"},
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


def public_transaction_types():
    """Types de mouvement envoyés au frontend, dans l'ordre d'affichage."""
    return [{"id": tid, **TYPES_TRANSACTION[tid]} for tid in ORDRE_TRANSACTIONS]


def public_classes():
    """Classes d'actifs envoyées au frontend, dans l'ordre d'affichage."""
    return [{"id": cid, **CLASSES_ACTIFS[cid]} for cid in ORDRE_CLASSES]


def classe_par_defaut(type_compte):
    """Classe proposée pour une position, d'après le type de son enveloppe."""
    return CLASSE_PAR_DEFAUT.get(type_compte, "autre")
