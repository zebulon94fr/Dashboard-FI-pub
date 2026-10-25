"""Import d'un relevé de courtier au format CSV dans le journal des mouvements.

Aucun courtier n'exporte le même fichier : les en-têtes, le séparateur, le
format des dates et celui des nombres changent de l'un à l'autre. Le module ne
cherche donc pas à reconnaître des courtiers, il reconnaît des *colonnes* — et
laisse corriger sa proposition avant d'écrire quoi que ce soit.

L'import se fait en deux temps, par le même code : `executer(..., valider=False)`
rend l'aperçu, `valider=True` écrit. Ce que montre l'aperçu est donc exactement
ce qui sera enregistré, ligne par ligne, y compris les erreurs et les doublons.
"""
import collections
import csv
import datetime
import io
import logging
import re
import unicodedata

from backend.db import get_db
from backend.positions import nombre
from backend.tableur import ORIGINE as TABLEUR_ORIGINE, TableurError, est_classeur, lire_xlsx
from backend.transactions import TransactionError, add_transaction, recalc_position
from catalog import ORDRE_TRANSACTIONS

log = logging.getLogger("dashboard")

# Colonnes que le journal sait utiliser. `libelle` sert à retrouver la position
# concernée ; `montant`, `credit` et `debit` portent les mouvements d'espèces,
# les relevés comptables ventilant les entrées et les sorties en deux colonnes.
CHAMPS = ("date", "type", "libelle", "isin", "quantite", "prix", "devise", "taux",
          "frais", "montant", "credit", "debit")

# Mots-clés cherchés dans les en-têtes. Un en-tête identique à un mot-clé
# l'emporte toujours sur un en-tête qui le contient (voir _proposer_correspondance) :
# sans cette règle, « Nb titres » serait pris pour le nom du titre.
INDICES_COLONNES = {
    "date":     ("date operation", "date d operation", "trade date", "date execution",
                 "date valeur", "date"),
    # « designation » et « description » ferment la liste : un fichier qui porte
    # une vraie colonne « Type » la garde, et un relevé qui n'en a pas — Bourse
    # Direct range le sens de l'opération dans « Désignation » — y trouve le sien.
    "type":     ("type operation", "type d operation", "operation", "nature", "sens",
                 "transaction", "type", "designation", "description"),
    # Les noms d'instrument passent avant les libellés ambigus : face à
    # « Désignation » et « Titre », c'est « Titre » qui nomme la ligne.
    "libelle":  ("titre", "valeur", "instrument", "produit", "libelle", "symbole",
                 "symbol", "ticker", "nom", "designation", "description",
                 "isin", "code isin"),
    # L'ISIN identifie une ligne sans ambiguïté, là où les noms divergent d'un
    # courtier à l'autre — « TOTALENERGIES SE » ici, « TotalEnergies » ailleurs.
    # Il reste listé dans `libelle` en dernier recours, pour un fichier sans nom.
    "isin":     ("isin", "code isin", "code valeur"),
    "quantite": ("quantite", "qte", "nombre de parts", "nombre", "quantity", "shares",
                 "nb titres"),
    # « cours » avant « px un brut » : sur un relevé Bourse Direct, le prix
    # unitaire d'une transaction est dans COURS, et PX UN.BRUT ne porte que le
    # dividende par titre — vide sur les achats et les ventes.
    "prix":     ("prix unitaire", "cours unitaire", "prix d execution", "cours",
                 "prix", "price", "px un brut", "px un"),
    "devise":   ("devise", "currency", "monnaie"),
    # Le taux du jour de l'opération, quand le relevé le donne : il fige le prix
    # de revient en euros au cours d'alors, sans interroger le marché — donc
    # sans dépendre du réseau au moment de l'import, ni d'un taux approché.
    "taux":     ("taux de change", "cours de change", "exchange rate", "fx rate", "taux"),
    "frais":    ("frais de courtage", "frais", "commission", "courtage", "fee", "fees"),
    "montant":  ("montant net", "montant brut", "montant total", "montant", "brut",
                 "net", "total", "amount"),
    "credit":   ("credit", "credit eur", "entree"),
    "debit":    ("debit", "debit eur", "sortie"),
}

# Mots-clés cherchés dans la colonne « type ». Ils sont cherchés comme des mots
# entiers, et non comme de simples fragments : « rachat partiel » désigne un
# retrait d'assurance-vie, et contient pourtant les lettres de « achat ».
INDICES_TYPES = {
    "vente":     ("vente", "vendre", "vendu", "cession", "sell", "sale", "liquidation"),
    "retrait":   ("retrait", "rachat", "withdrawal", "sortie", "desinvestissement"),
    "achat":     ("achat", "acheter", "achete", "acquisition", "souscription", "buy",
                  "purchase"),
    "versement": ("versement", "virement", "depot", "deposit", "apport",
                  "alimentation", "contribution", "investissement"),
    # La taxe sur les transactions financières est un frais comme un autre du
    # point de vue du journal : de l'argent qui sort, daté.
    "frais":     ("frais", "commission", "droits de garde", "droits", "taxe", "taxes",
                  "impot", "impots", "fee", "charge"),
    # Un dividende n'est pas un mouvement du journal : il a sa propre table, et
    # l'import l'y dirige plutôt que de le refuser ou d'en faire un versement.
    "dividende": ("coupon", "coupons", "dividende", "dividend", "interets",
                  "interet", "revenu", "revenus"),
}

TYPE_DIVIDENDE = "dividende"

FORMATS_DATE = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d",
                "%d/%m/%y", "%m/%d/%Y")

LIGNES_APERCU = 5
TAILLE_MAX = 5 * 1024 * 1024


# ══════════════════════════════════════════════════════════════
# NORMALISATION
# ══════════════════════════════════════════════════════════════
def _sans_accents(texte):
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _entete(texte):
    """En-tête ramené à des mots simples : « Date d'opération » -> « date d operation »."""
    return re.sub(r"[^a-z0-9]+", " ", _sans_accents(texte).lower()).strip()


def _cle(texte):
    """Clé de rapprochement d'un libellé : sans accents, sans ponctuation, en capitales."""
    return re.sub(r"[^A-Z0-9]+", "", _sans_accents(texte or "").upper())


def _decoder(contenu):
    """Texte du fichier, quel que soit son encodage. Les relevés français sont souvent en latin-1."""
    if isinstance(contenu, str):
        return contenu
    for encodage in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return contenu.decode(encodage)
        except UnicodeDecodeError:
            continue
    return contenu.decode("latin-1", errors="replace")


def _lire(contenu):
    """
    (en-têtes, lignes, format) du fichier, qu'il soit CSV ou classeur.

    Le format se reconnaît au contenu et non à l'extension : un fichier
    renommé reste ce qu'il est, et un classeur commence toujours par la
    signature d'une archive zip.
    """
    if est_classeur(contenu):
        try:
            entetes, lignes = lire_xlsx(contenu)
        except TableurError as e:
            raise TransactionError(str(e))
        return entetes, lignes, "xlsx"

    texte = _decoder(contenu)
    if len(texte) > TAILLE_MAX:
        raise TransactionError(
            f"Fichier trop volumineux ({len(texte) // 1024} Ko) : la limite est de "
            f"{TAILLE_MAX // 1024 // 1024} Mo. Découpez-le par année."
        )
    texte = texte.lstrip("﻿\r\n")
    if not texte.strip():
        raise TransactionError("Le fichier est vide.")

    echantillon = texte[:8192]
    try:
        separateur = csv.Sniffer().sniff(echantillon, delimiters=";,\t|").delimiter
    except csv.Error:
        # Sans verdict du renifleur, le séparateur le plus fréquent de la
        # première ligne tranche mieux qu'un défaut arbitraire.
        premiere = echantillon.splitlines()[0]
        separateur = max(";,\t|", key=premiere.count)
        if premiere.count(separateur) == 0:
            raise TransactionError(
                "Aucun séparateur reconnu (point-virgule, virgule, tabulation ou barre "
                "verticale). Vérifiez qu'il s'agit bien d'un fichier CSV."
            )

    lecteur = csv.reader(io.StringIO(texte), delimiter=separateur)
    lignes = [ligne for ligne in lecteur if any((c or "").strip() for c in ligne)]
    if len(lignes) < 2:
        raise TransactionError(
            "Le fichier ne contient qu'une ligne : il faut un en-tête et au moins un mouvement."
        )
    return [c.strip() for c in lignes[0]], lignes[1:], separateur


# ══════════════════════════════════════════════════════════════
# ANALYSE
# ══════════════════════════════════════════════════════════════
def _colonnes_servies(lignes, maximum=200):
    """
    Colonnes qui portent une vraie donnée dans l'échantillon.

    Un relevé traîne des colonnes vides ou à zéro d'un bout à l'autre —
    « COMMISSION » quand les frais sont en réalité dans « COURTAGE » — et leur
    en-tête seul ne dit pas laquelle fait foi. Un zéro ne compte donc pas comme
    une donnée : c'est la colonne jumelle, servie, qu'il faut proposer.
    """
    servies = set()
    for ligne in lignes[:maximum]:
        for i, valeur in enumerate(ligne):
            texte = (valeur or "").strip()
            if not texte:
                continue
            lu = nombre(texte, defaut=None)
            if lu is None or lu != 0:
                servies.add(i)
    return servies


PART_TYPES_RECONNUS = 0.60      # au-delà, une colonne décrit bien des opérations


def _colonne_types(normalises, lignes, maximum=200):
    """
    Colonne dont le contenu ressemble le plus à des types d'opération.

    On lit les valeurs, pas l'en-tête : la colonne retenue est celle dont la
    plupart des cases se reconnaissent en achat, vente, versement, retrait,
    frais ou dividende. Sous `PART_TYPES_RECONNUS`, aucune ne convainc et
    c'est aux mots-clés d'en-tête de trancher.
    """
    meilleure, meilleur_score = None, 0.0
    for index in range(len(normalises)):
        valeurs = [(l[index] or "").strip() for l in lignes[:maximum] if index < len(l)]
        valeurs = [v for v in valeurs if v]
        if not valeurs:
            continue
        score = sum(1 for v in valeurs if _type(v)) / len(valeurs)
        if score > meilleur_score:
            meilleure, meilleur_score = index, score
    return meilleure if meilleur_score >= PART_TYPES_RECONNUS else None


def _proposer_correspondance(entetes, lignes=()):
    """
    Colonne proposée pour chaque champ, par mots-clés d'en-tête.

    Quatre passes, de la plus sûre à la plus permissive : égalité d'en-tête sur
    une colonne servie, inclusion sur une colonne servie, puis les deux mêmes
    sur les colonnes vides. L'égalité passe avant l'inclusion, sans quoi le
    premier champ servi raflerait une colonne qui appartient à un autre —
    « Nb titres » pris pour un titre. Et une colonne servie passe avant une
    colonne vide de même nom, parce qu'un en-tête ne vaut que ce qu'il porte.
    """
    normalises = [_entete(e) for e in entetes]
    servies = _colonnes_servies(lignes) if lignes else set(range(len(entetes)))
    correspondance, prises = {}, set()

    # Le sens d'une opération se reconnaît à ce qu'une colonne contient, pas à
    # son titre : un relevé peut porter une colonne « Type » qui dit
    # « Opération » et une colonne « Événement » qui dit « Acheter 2 @ 458.25 ».
    # Seule la seconde décide, et seul son contenu le révèle.
    colonne_types = _colonne_types(normalises, lignes)
    if colonne_types is not None:
        correspondance["type"] = colonne_types
        prises.add(colonne_types)

    for exact, servie_dabord in ((True, True), (False, True), (True, False), (False, False)):
        for champ, indices in INDICES_COLONNES.items():
            if champ in correspondance:
                continue
            for indice in indices:
                trouve = next(
                    (i for i, e in enumerate(normalises)
                     if i not in prises
                     and (not servie_dabord or i in servies)
                     and (e == indice if exact else indice in e)), None)
                if trouve is not None:
                    correspondance[champ] = trouve
                    prises.add(trouve)
                    break
    return correspondance


def analyser(contenu):
    """En-têtes, aperçu et correspondance proposée — sans rien interpréter encore."""
    entetes, lignes, separateur = _lire(contenu)
    return {
        "colonnes": entetes,
        "separateur": separateur,
        "nb_lignes": len(lignes),
        "apercu": [list(ligne) for ligne in lignes[:LIGNES_APERCU]],
        "correspondance": _proposer_correspondance(entetes, lignes),
    }


# ══════════════════════════════════════════════════════════════
# INTERPRÉTATION D'UNE LIGNE
# ══════════════════════════════════════════════════════════════
def _date(valeur):
    texte = (valeur or "").strip()[:10].replace(" ", "")
    for format_ in FORMATS_DATE:
        try:
            return datetime.datetime.strptime(texte, format_).date().isoformat()
        except ValueError:
            continue
    # Un entier à cinq chiffres dans une colonne de dates est un numéro de
    # série Excel qu'aucun style n'a signalé — le cas d'un CSV exporté depuis
    # un tableur. La fourchette retenue couvre 1954 à 2064 : assez large pour
    # un relevé, assez étroite pour ne pas prendre un montant pour une date.
    if re.fullmatch(r"\d{5}", texte) and 20000 <= int(texte) <= 60000:
        return (TABLEUR_ORIGINE + datetime.timedelta(days=int(texte))).isoformat()
    return None


def _quantite_prix(texte):
    """
    Quantité et prix extraits d'un libellé d'opération, ou None.

    Certains courtiers ne donnent ni colonne de quantité ni colonne de prix :
    tout tient dans la phrase de l'opération — « Acheter 2 @ 458.25 USD ». La
    forme « nombre @ nombre » est assez caractéristique pour être lue, et
    assez rare pour ne rien capter d'autre par accident.
    """
    m = re.search(r"(-?[\d][\d\s.,]*)\s*@\s*([\d][\d\s.,]*)\s*([A-Za-z]{3})?", texte or "")
    if not m:
        return None
    quantite, prix = abs(nombre(m.group(1))), abs(nombre(m.group(2)))
    if quantite <= 0 or prix <= 0:
        return None
    return quantite, prix, (m.group(3) or "").upper()


def _type(valeur, defaut=""):
    texte = _sans_accents(valeur or "").lower()
    # Une annulation n'est pas l'opération qu'elle annule : la reprendre comme
    # telle compterait deux fois un dividende que le courtier a repris.
    if any(mot in texte for mot in ("contre-passation", "contre passation",
                                    "annulation", "annule", "storno")):
        return ""
    for type_tx, indices in INDICES_TYPES.items():
        if any(re.search(rf"\b{re.escape(indice)}", texte) for indice in indices):
            return type_tx
    return defaut


def _valeur(ligne, correspondance, champ):
    index = correspondance.get(champ)
    if index is None or index >= len(ligne):
        return ""
    return (ligne[index] or "").strip()


def _index_positions(db, account_id):
    """Positions du compte, indexées par ticker, ISIN et nom normalisés."""
    index = {}
    for row in db.execute(
        "SELECT id, nom, ticker, isin, devise FROM positions WHERE account_id=?",
        (account_id,),
    ):
        for champ in ("ticker", "isin", "nom"):
            cle = _cle(row[champ])
            if cle:
                index.setdefault(cle, dict(row))
    return index


def _rapprocher(index_positions, brut):
    """
    Position visée par une ligne : par ISIN d'abord, par libellé ensuite.

    Un ISIN est le même partout ; un nom, non — « TOTALENERGIES SE » chez un
    courtier et « TotalEnergies » au portefeuille désignent la même ligne, et
    seul le code les réunit.
    """
    for cle in (_cle(brut.get("isin")), _cle(brut.get("libelle"))):
        if cle and cle in index_positions:
            return index_positions[cle]
    return None


def _signature(date, type_tx, nom, quantite, prix, montant):
    """
    Empreinte d'un mouvement, pour repérer ce qui est déjà au journal.

    Un achat s'identifie par sa ligne, sa quantité et son prix ; un mouvement
    d'espèces par son seul montant. C'est la même règle des deux côtés de la
    comparaison, sans quoi aucun doublon ne serait jamais reconnu. Les frais en
    sont exclus : deux exports du même ordre les ventilent parfois autrement.
    """
    if type_tx in ("achat", "vente"):
        return (date, type_tx, _cle(nom), round(quantite or 0, 6), round(prix or 0, 6), 0.0)
    return (date, type_tx, "", 0.0, 0.0, round(montant or 0, 2))


def _signatures_existantes(db, account_id):
    """
    Combien de fois le compte porte déjà chaque empreinte — journal et dividendes.

    Un décompte, et non un ensemble : une même opération peut légitimement
    figurer deux fois — deux dividendes d'un même titre versés le même jour —
    et c'est le nombre d'exemplaires déjà en base qui dit combien d'un import
    font doublon.
    """
    connues = collections.Counter()
    for r in db.execute(
        "SELECT date, type, nom, quantite, prix, montant_eur FROM transactions "
        "WHERE account_id=?", (account_id,)
    ):
        connues[_signature(r["date"], r["type"], r["nom"], r["quantite"],
                           r["prix"], r["montant_eur"])] += 1
    for r in db.execute(
        "SELECT date, nom, montant FROM dividendes WHERE account_id=?", (account_id,)
    ):
        connues[("dividende", r["date"], _cle(r["nom"]), round(r["montant"], 2))] += 1
    return connues


# ══════════════════════════════════════════════════════════════
# IMPORT
# ══════════════════════════════════════════════════════════════
def executer(contenu, account_id, correspondance, options=None, valider=False):
    """
    Interprète le fichier et, si `valider`, inscrit les mouvements au journal.

    Retourne une ligne de compte rendu par ligne du fichier, avec son statut :
    `ok`, `doublon` (déjà au journal) ou `erreur` (et la raison). L'aperçu et
    l'import empruntent le même chemin : ce qui est montré est ce qui est écrit.
    """
    options = options or {}
    creer_positions = bool(options.get("creer_positions", True))
    # « actuel » : la quantité saisie est celle d'aujourd'hui, l'ouverture se
    # déduit à rebours. « ouverture » : elle précède le relevé. « non » : le
    # journal importé fait seul la quantité.
    conserver = (options.get("conserver_existant") or "actuel").strip().lower()
    type_defaut = (options.get("type_defaut") or "").strip().lower()
    devise_defaut = (options.get("devise_defaut") or "EUR").strip().upper()

    correspondance = {c: int(i) for c, i in (correspondance or {}).items()
                      if c in CHAMPS and str(i).strip() != "" and int(i) >= 0}
    if "date" not in correspondance:
        raise TransactionError(
            "Indiquez quelle colonne porte la date : sans elle, aucun mouvement ne peut "
            "être daté, et c'est la date qui fait le TWR et le TRI."
        )

    _entetes, lignes, _sep = _lire(contenu)

    with get_db() as db:
        if not db.execute("SELECT id FROM accounts WHERE id=?", (account_id,)).fetchone():
            raise TransactionError("Compte introuvable.")
        index_positions = _index_positions(db, account_id)
        deja_vues = _signatures_existantes(db, account_id)
        # Ce que le journal du compte explique déjà, pour ne pas alerter sur
        # une vente dont l'achat a été importé lors d'un passage précédent.
        quantites_connues = {}
        for row in db.execute("""
            SELECT nom, SUM(CASE WHEN type='achat' THEN quantite ELSE -quantite END) solde
            FROM transactions WHERE account_id=? AND type IN ('achat','vente')
            GROUP BY nom
        """, (account_id,)):
            quantites_connues[_cle(row["nom"])] = max(0.0, row["solde"] or 0.0)

    rapport, a_ecrire = [], []
    for numero, ligne in enumerate(lignes, start=2):      # 1 = l'en-tête
        compte_rendu = _interpreter(ligne, numero, correspondance, type_defaut,
                                    devise_defaut, index_positions)
        signature = compte_rendu.pop("_signature", None)
        if compte_rendu["statut"] == "ok":
            # Seul ce que la base contient déjà fait doublon, et autant de fois
            # qu'elle le contient. Deux lignes identiques d'un même relevé sont
            # deux opérations réelles : les confondre en supprimerait une.
            if deja_vues.get(signature, 0) > 0:
                deja_vues[signature] -= 1
                compte_rendu["statut"] = "doublon"
                compte_rendu["message"] = "Déjà présent au journal, à la même date et au même prix."
            else:
                a_ecrire.append(compte_rendu)
        rapport.append(compte_rendu)

    # Les ouvertures précèdent le contrôle de stock : ce qu'elles expliquent
    # n'est plus une vente sans origine.
    ouvertures = []
    if conserver in ("actuel", "ouverture"):
        with get_db() as db:
            ouvertures = _ouvertures(db, a_ecrire, conserver)
        reelles = [o for o in ouvertures if o["statut"] == "ouverture"]
        a_ecrire = reelles + a_ecrire
        rapport = ouvertures + rapport
    alertes = _controler_stocks(a_ecrire, quantites_connues)

    resume = {
        "total": len(rapport),
        "alertes": alertes,
        "ouvertures": sum(1 for o in ouvertures if o["statut"] == "ouverture"),
        "a_importer": sum(1 for l in rapport if l["statut"] in ("ok", "alerte", "ouverture")),
        "doublons": sum(1 for l in rapport if l["statut"] == "doublon"),
        "erreurs": sum(1 for l in rapport if l["statut"] == "erreur"),
        "dividendes": sum(1 for l in a_ecrire if l["type"] == TYPE_DIVIDENDE),
        "positions_a_creer": sorted({l["libelle"] for l in a_ecrire
                                     if l["statut"] == "ok" and not l["position_id"]
                                     and l["sur_ligne"]}),
        "importes": 0,
    }
    if not creer_positions:
        resume["positions_a_creer"] = []

    if valider:
        resume["importes"] = _ecrire(a_ecrire, account_id, creer_positions, index_positions)

    return {"lignes": rapport, "resume": resume}


def _interpreter(ligne, numero, correspondance, type_defaut, devise_defaut, index_positions):
    """Une ligne du fichier traduite en mouvement, ou en erreur expliquée."""
    brut = {champ: _valeur(ligne, correspondance, champ) for champ in CHAMPS}
    resultat = {
        "numero": numero, "date": "", "type": "", "libelle": brut["libelle"],
        "isin": brut["isin"].strip().upper(), "taux": None,
        "quantite": 0.0, "prix": 0.0, "devise": devise_defaut, "frais": 0.0,
        "montant": 0.0, "position_id": None, "position_nom": "", "sur_ligne": False,
        "statut": "erreur", "message": "",
    }

    date = _date(brut["date"])
    if not date:
        resultat["message"] = (f"Date illisible : « {brut['date']} ». "
                               "Formats reconnus : AAAA-MM-JJ, JJ/MM/AAAA, JJ-MM-AAAA.")
        return resultat
    resultat["date"] = date

    type_tx = _type(brut["type"], type_defaut)
    if type_tx not in ORDRE_TRANSACTIONS and type_tx != TYPE_DIVIDENDE:
        resultat["message"] = (
            f"Type de mouvement non reconnu : « {brut['type']} ». "
            "Choisissez un type par défaut, ou désignez la bonne colonne."
            if brut["type"] else
            "Aucun type de mouvement : désignez la colonne qui le porte, ou choisissez un type par défaut."
        )
        return resultat
    resultat["type"] = type_tx

    # Le signe de la quantité est redondant avec le type du mouvement, et les
    # relevés ne s'accordent pas sur sa convention : seule la valeur compte.
    quantite = abs(nombre(brut["quantite"]))
    prix = abs(nombre(brut["prix"]))
    # Un relevé comptable ventile les entrées et les sorties en deux colonnes,
    # dont une seule est servie par ligne.
    montant = (abs(nombre(brut["montant"])) or abs(nombre(brut["credit"]))
               or abs(nombre(brut["debit"])))
    frais = abs(nombre(brut["frais"]))
    devise = (brut["devise"] or devise_defaut).strip().upper()[:3] or devise_defaut
    taux = nombre(brut["taux"]) if brut["taux"] else 0.0
    resultat.update({"quantite": quantite, "prix": prix, "montant": montant,
                     "frais": frais, "devise": devise,
                     "taux": taux if taux > 0 else None})

    sur_ligne = type_tx in ("achat", "vente")
    resultat["sur_ligne"] = sur_ligne

    if type_tx == TYPE_DIVIDENDE:
        # Le rapprochement sert ici au nom : « FR0000120271 » dans un relevé
        # devient « TotalEnergies » si la ligne existe déjà au portefeuille.
        trouvee = _rapprocher(index_positions, brut)
        if trouvee:
            resultat["position_id"] = trouvee["id"]
            resultat["position_nom"] = trouvee["nom"]
        if montant <= 0:
            resultat["message"] = ("Un dividende demande un montant : désignez la colonne "
                                   "qui le porte (montant, crédit ou brut).")
            return resultat
        if not brut["libelle"]:
            resultat["message"] = "Aucun libellé : un dividende se rattache à une ligne nommée."
            return resultat
        resultat["statut"] = "ok"
        resultat["_signature"] = ("dividende", date,
                                  _cle(resultat["position_nom"] or brut["libelle"]),
                                  round(montant, 2))
        return resultat

    if sur_ligne:
        # Faute de colonnes, quantité et prix se lisent dans la phrase de
        # l'opération : « Acheter 2 @ 458.25 USD » les porte toutes les deux,
        # et la devise avec.
        if quantite <= 0 or prix <= 0:
            extrait = _quantite_prix(brut["type"])
            if extrait:
                quantite = quantite or extrait[0]
                prix = prix or extrait[1]
                if extrait[2] and not brut["devise"]:
                    devise = extrait[2]
                resultat.update({"quantite": quantite, "prix": prix, "devise": devise})

        # Un relevé donne parfois le montant sans le prix unitaire : l'un se
        # déduit de l'autre dès que la quantité est connue.
        if quantite <= 0:
            resultat["message"] = ("Un achat ou une vente demande une quantité supérieure "
                                   "à zéro : désignez la colonne qui la porte.")
            return resultat
        if prix <= 0 and montant > 0:
            prix = round(montant / quantite, 6)
            resultat["prix"] = prix
        if prix <= 0:
            resultat["message"] = "Ni prix unitaire ni montant : le mouvement ne peut pas être valorisé."
            return resultat
        if not brut["libelle"]:
            resultat["message"] = "Aucun libellé : impossible de savoir quelle ligne est concernée."
            return resultat

        trouvee = _rapprocher(index_positions, brut)
        if trouvee:
            resultat["position_id"] = trouvee["id"]
            resultat["position_nom"] = trouvee["nom"]

        # Quand le relevé donne le montant réellement porté au compte et
        # qu'aucune colonne ne chiffre les frais, l'écart avec quantité × prix
        # × taux les chiffre : un achat les paie en plus, une vente les retient
        # sur le produit. Le garde-fou des 5 % écarte le cas d'une colonne
        # « montant » qui compterait tout autre chose.
        brut_eur = quantite * prix * (resultat["taux"] or 1.0)
        if frais <= 0 and montant > 0 and brut_eur > 0:
            ecart = abs(montant - brut_eur)
            if ecart <= brut_eur * 0.05:
                resultat["frais"] = round(ecart, 2)

        resultat["montant"] = round(quantite * prix, 2)
    else:
        if montant <= 0:
            montant = round(quantite * prix, 2) if quantite and prix else 0.0
            resultat["montant"] = montant
        if montant <= 0:
            resultat["message"] = (
                f"Un mouvement « {type_tx} » demande un montant supérieur à zéro : "
                "désignez la colonne qui le porte.")
            return resultat

    resultat["statut"] = "ok"
    # `add_transaction` enregistre le nom de la position, pas le libellé du
    # relevé : l'empreinte doit suivre, sinon un second import ne reconnaîtrait
    # jamais ses propres écritures dès que les deux noms diffèrent.
    resultat["_signature"] = _signature(
        date, type_tx, resultat["position_nom"] or brut["libelle"],
        quantite, resultat["prix"], resultat["montant"])
    return resultat


def _ouvertures(db, a_ecrire, mode="actuel"):
    """
    Achats d'ouverture à inscrire pour les lignes déjà détenues sans journal.

    Dès qu'un achat ou une vente est importé sur une position, le journal
    devient la source de vérité de sa quantité : une saisie manuelle que rien
    n'adosse à des mouvements serait écrasée, et une ligne de 330 titres dont
    le relevé n'explique que les 80 derniers fondrait en silence.

    Reste à savoir ce que dit la quantité saisie, et les deux lectures mènent
    à des portefeuilles différents :

      * `actuel` — c'est ce qui est détenu aujourd'hui, ce que montre l'onglet
        Positions. L'ouverture se déduit alors à rebours des mouvements
        importés, et le total ne bouge pas : l'import ajoute une histoire, pas
        du capital.
      * `ouverture` — c'est ce qui était détenu avant le relevé, dont les
        mouvements s'ajoutent par-dessus.

    L'ouverture est datée de la veille du premier mouvement importé qui
    concerne la ligne : la seule date dont on soit sûr qu'elle précède tout ce
    que le relevé raconte.
    """
    premiere_date, variation = {}, {}
    for ligne in a_ecrire:
        if not (ligne["sur_ligne"] and ligne["position_id"]):
            continue
        identifiant = ligne["position_id"]
        if identifiant not in premiere_date or ligne["date"] < premiere_date[identifiant]:
            premiere_date[identifiant] = ligne["date"]
        signe = 1 if ligne["type"] == "achat" else -1
        variation[identifiant] = variation.get(identifiant, 0.0) + signe * ligne["quantite"]
    if not premiere_date:
        return []

    marques = ",".join("?" * len(premiere_date))
    sans_journal = {
        r["id"]: r for r in db.execute(f"""
            SELECT p.id, p.nom, p.quantite, p.pru, p.devise, p.taux_change
            FROM positions p
            WHERE p.id IN ({marques}) AND p.quantite > 0 AND p.pru > 0
              AND NOT EXISTS (SELECT 1 FROM transactions t
                              WHERE t.position_id = p.id AND t.type IN ('achat','vente'))
        """, list(premiere_date))
    }

    ouvertures = []
    for identifiant, position in sans_journal.items():
        detenue = position["quantite"]
        quantite = detenue - variation.get(identifiant, 0.0) if mode == "actuel" else detenue
        veille = (datetime.date.fromisoformat(premiere_date[identifiant])
                  - datetime.timedelta(days=1)).isoformat()

        if quantite <= 1e-9:
            # Le relevé achète plus qu'il n'en reste : la saisie manuelle n'est
            # pas la photo d'aujourd'hui, ou elle précède une partie du relevé.
            # Rien à ouvrir, mais l'utilisateur doit savoir que sa quantité va
            # être refaite à partir des seuls mouvements importés.
            ouvertures.append({
                "numero": 0, "date": veille, "type": "", "libelle": position["nom"],
                "isin": "", "taux": None, "quantite": 0.0, "prix": 0.0,
                "devise": position["devise"], "frais": 0.0, "montant": 0.0,
                "position_id": identifiant, "position_nom": position["nom"],
                "sur_ligne": False, "statut": "alerte",
                "message": (
                    f"{detenue:g} titres saisis, mais le relevé en achète "
                    f"{variation.get(identifiant, 0.0):+g} net : la quantité sera refaite "
                    "depuis le relevé seul. Vérifiez cette ligne après l'import."),
            })
            continue

        ouvertures.append({
            "numero": 0, "date": veille, "type": "achat", "libelle": position["nom"],
            "isin": "", "taux": position["taux_change"], "quantite": quantite,
            "prix": position["pru"], "devise": position["devise"], "frais": 0.0,
            "montant": round(quantite * position["pru"], 2),
            "position_id": identifiant, "position_nom": position["nom"],
            "sur_ligne": True, "statut": "ouverture",
            "message": (
                f"{quantite:g} titres inscrits au {veille} : avec les mouvements du relevé, "
                f"la ligne retombe sur les {detenue:g} titres détenus."
                if mode == "actuel" else
                f"{quantite:g} titres déjà détenus, inscrits au {veille} avant les "
                "mouvements du relevé."),
        })
    return ouvertures


def _controler_stocks(a_ecrire, quantites_connues):
    """
    Signale les ventes qui portent sur plus de titres que le relevé n'en explique.

    C'est le symptôme d'un relevé qui commence après l'acquisition : les titres
    vendus ont été achetés avant la première ligne du fichier. Le prix moyen
    pondéré ne peut alors pas être reconstitué, et la plus-value réalisée qui
    en découlerait serait fausse — mieux vaut le dire que l'afficher.
    """
    stocks = dict(quantites_connues)
    alertes = 0
    for ligne in sorted(a_ecrire, key=lambda l: l["date"]):
        if not ligne["sur_ligne"]:
            continue
        cle = _cle(ligne["libelle"])
        if ligne["type"] == "achat":
            stocks[cle] = stocks.get(cle, 0.0) + ligne["quantite"]
            continue
        disponible = stocks.get(cle, 0.0)
        if ligne["quantite"] > disponible + 1e-9:
            manque = ligne["quantite"] - disponible
            ligne["statut"] = "alerte"
            ligne["message"] = (
                f"Vente de {ligne['quantite']:g} titres alors que {disponible:g} seulement "
                f"sont expliqués à cette date : {manque:g} viennent d'un achat antérieur au "
                "relevé. Le prix de revient et la plus-value de cette ligne seront faux tant "
                "que la position d'ouverture n'est pas saisie."
            )
            alertes += 1
        stocks[cle] = max(0.0, disponible - ligne["quantite"])
    return alertes


def _ecrire_ligne(ligne, account_id, creer_positions, index_positions, touchees,
                  add_dividende, create_position):
    """Écrit une ligne retenue, en créant au besoin la position absente."""
    # Un dividende n'entre pas au journal : il alimente l'onglet Dividendes,
    # d'où sortent le rendement par ligne et le revenu annuel.
    if ligne["type"] == TYPE_DIVIDENDE:
        add_dividende({
            "date": ligne["date"], "account_id": account_id,
            "nom": ligne["position_nom"] or ligne["libelle"],
            "montant": ligne["montant"], "note": "Importé d'un relevé",
        })
        return

    position_id = ligne["position_id"]

    if ligne["sur_ligne"] and not position_id:
        if not creer_positions:
            raise TransactionError(
                "Position absente du compte, et la création des lignes manquantes est désactivée.")
        cle = _cle(ligne["isin"]) or _cle(ligne["libelle"])
        connue = index_positions.get(cle) or index_positions.get(_cle(ligne["libelle"]))
        if connue:
            position_id = connue["id"]
        else:
            # Quantité et PRU restent à zéro : c'est le journal qui les
            # établira au recalcul, à partir des mouvements importés.
            position_id = create_position(account_id, {
                "nom": ligne["libelle"][:120], "isin": ligne["isin"],
                "quantite": 0, "pru": 0,
                "cours": ligne["prix"], "devise": ligne["devise"],
                "taux_change": 1.0 if ligne["devise"] == "EUR" else ligne["taux"],
            })
            nouvelle = {"id": position_id, "nom": ligne["libelle"],
                        "ticker": "", "isin": ligne["isin"], "devise": ligne["devise"]}
            index_positions[cle] = nouvelle
            if _cle(ligne["isin"]):
                index_positions[_cle(ligne["isin"])] = nouvelle

    mouvement = {
        "date": ligne["date"], "account_id": account_id, "type": ligne["type"],
        "frais": ligne["frais"], "note": "Importé d'un relevé",
    }
    if ligne["sur_ligne"]:
        mouvement.update({
            "position_id": position_id, "quantite": ligne["quantite"],
            "prix": ligne["prix"], "devise": ligne["devise"],
            # Le taux du relevé, quand il est là : c'est celui du jour de
            # l'opération, et il fige le prix de revient sans appel réseau.
            "taux_change": ligne["taux"],
        })
        touchees.add(position_id)
    else:
        mouvement["montant"] = ligne["montant"]

    add_transaction(mouvement)


def _ecrire(lignes, account_id, creer_positions, index_positions):
    """Inscrit les mouvements retenus, en créant au besoin les positions absentes."""
    from backend.dividendes import add_dividende
    from backend.positions import create_position

    importes, touchees = 0, set()
    for ligne in lignes:
        try:
            _ecrire_ligne(ligne, account_id, creer_positions, index_positions,
                          touchees, add_dividende, create_position)
        except Exception as e:
            # Un import à moitié écrit sans rien dire serait pire qu'un refus :
            # la ligne fautive est rapportée, les autres passent.
            ligne["statut"] = "erreur"
            ligne["message"] = f"Écriture impossible : {e}"
            log.warning(f"Import, ligne {ligne['numero']} : {e}")
            continue
        importes += 1

    # `add_transaction` recalcule déjà la position à chaque écriture ; un
    # dernier passage garantit l'ordre chronologique du PMP.
    for position_id in touchees:
        recalc_position(position_id)
    return importes
