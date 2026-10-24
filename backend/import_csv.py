"""Import d'un relevé de courtier au format CSV dans le journal des mouvements.

Aucun courtier n'exporte le même fichier : les en-têtes, le séparateur, le
format des dates et celui des nombres changent de l'un à l'autre. Le module ne
cherche donc pas à reconnaître des courtiers, il reconnaît des *colonnes* — et
laisse corriger sa proposition avant d'écrire quoi que ce soit.

L'import se fait en deux temps, par le même code : `executer(..., valider=False)`
rend l'aperçu, `valider=True` écrit. Ce que montre l'aperçu est donc exactement
ce qui sera enregistré, ligne par ligne, y compris les erreurs et les doublons.
"""
import csv
import datetime
import io
import re
import unicodedata

from backend.db import get_db
from backend.positions import nombre
from backend.transactions import TransactionError, add_transaction, recalc_position
from catalog import ORDRE_TRANSACTIONS

# Colonnes que le journal sait utiliser. `libelle` sert à retrouver la position
# concernée ; `montant` ne sert qu'aux mouvements d'espèces.
CHAMPS = ("date", "type", "libelle", "quantite", "prix", "devise", "frais", "montant")

# Mots-clés cherchés dans les en-têtes, du plus spécifique au plus général :
# « prix de revient » ne doit pas être pris pour « prix ».
INDICES_COLONNES = {
    "date":     ("date operation", "date d operation", "trade date", "date execution",
                 "date valeur", "date"),
    "type":     ("type operation", "type d operation", "operation", "nature", "sens",
                 "transaction", "type"),
    "libelle":  ("libelle", "designation", "instrument", "produit", "valeur", "titre",
                 "description", "nom", "symbole", "symbol", "ticker", "isin", "code isin"),
    "quantite": ("quantite", "qte", "nombre de parts", "nombre", "quantity", "shares",
                 "nb titres"),
    "prix":     ("prix unitaire", "cours unitaire", "prix d execution", "prix", "cours",
                 "price"),
    "devise":   ("devise", "currency", "monnaie"),
    "frais":    ("frais de courtage", "frais", "commission", "courtage", "fee", "fees"),
    "montant":  ("montant net", "montant brut", "montant total", "montant", "net",
                 "total", "amount"),
}

# Mots-clés cherchés dans la colonne « type ». Ils sont cherchés comme des mots
# entiers, et non comme de simples fragments : « rachat partiel » désigne un
# retrait d'assurance-vie, et contient pourtant les lettres de « achat ».
INDICES_TYPES = {
    "vente":     ("vente", "vendu", "cession", "sell", "sale", "liquidation"),
    "retrait":   ("retrait", "rachat", "withdrawal", "sortie", "desinvestissement"),
    "achat":     ("achat", "achete", "acquisition", "souscription", "buy", "purchase"),
    "versement": ("versement", "virement", "depot", "deposit", "apport", "alimentation",
                  "contribution"),
    "frais":     ("frais", "commission", "droits de garde", "fee", "charge"),
}

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
    """(en-têtes, lignes) du CSV, séparateur détecté. Lève une erreur parlante si illisible."""
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
def _proposer_correspondance(entetes):
    """Colonne du fichier proposée pour chaque champ, par mots-clés d'en-tête."""
    normalises = [_entete(e) for e in entetes]
    correspondance, prises = {}, set()
    for champ, indices in INDICES_COLONNES.items():
        for indice in indices:
            trouve = next(
                (i for i, e in enumerate(normalises)
                 if i not in prises and (e == indice or indice in e)), None)
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
        "correspondance": _proposer_correspondance(entetes),
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
    return None


def _type(valeur, defaut=""):
    texte = _sans_accents(valeur or "").lower()
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
    return {
        _signature(r["date"], r["type"], r["nom"], r["quantite"], r["prix"], r["montant_eur"])
        for r in db.execute(
            "SELECT date, type, nom, quantite, prix, montant_eur FROM transactions "
            "WHERE account_id=?", (account_id,))
    }


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

    rapport, a_ecrire = [], []
    for numero, ligne in enumerate(lignes, start=2):      # 1 = l'en-tête
        compte_rendu = _interpreter(ligne, numero, correspondance, type_defaut,
                                    devise_defaut, index_positions)
        signature = compte_rendu.pop("_signature", None)
        if compte_rendu["statut"] == "ok":
            if signature in deja_vues:
                compte_rendu["statut"] = "doublon"
                compte_rendu["message"] = "Déjà présent au journal, à la même date et au même prix."
            else:
                deja_vues.add(signature)
                a_ecrire.append(compte_rendu)
        rapport.append(compte_rendu)

    resume = {
        "total": len(rapport),
        "a_importer": sum(1 for l in rapport if l["statut"] == "ok"),
        "doublons": sum(1 for l in rapport if l["statut"] == "doublon"),
        "erreurs": sum(1 for l in rapport if l["statut"] == "erreur"),
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
    if type_tx not in ORDRE_TRANSACTIONS:
        resultat["message"] = (
            f"Type de mouvement non reconnu : « {brut['type']} ». "
            "Choisissez un type par défaut, ou désignez la bonne colonne."
            if brut["type"] else
            "Aucun type de mouvement : désignez la colonne qui le porte, ou choisissez un type par défaut."
        )
        return resultat
    resultat["type"] = type_tx

    quantite = nombre(brut["quantite"])
    prix = nombre(brut["prix"])
    montant = abs(nombre(brut["montant"]))
    frais = abs(nombre(brut["frais"]))
    devise = (brut["devise"] or devise_defaut).strip().upper()[:3] or devise_defaut
    resultat.update({"quantite": quantite, "prix": prix, "montant": montant,
                     "frais": frais, "devise": devise})

    sur_ligne = type_tx in ("achat", "vente")
    resultat["sur_ligne"] = sur_ligne

    if sur_ligne:
        # Un relevé donne parfois le montant sans le prix unitaire : l'un se
        # déduit de l'autre dès que la quantité est connue.
        if quantite <= 0:
            resultat["message"] = "Un achat ou une vente demande une quantité supérieure à zéro."
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

        trouvee = index_positions.get(_cle(brut["libelle"]))
        if trouvee:
            resultat["position_id"] = trouvee["id"]
            resultat["position_nom"] = trouvee["nom"]
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
    resultat["_signature"] = _signature(date, type_tx, brut["libelle"],
                                        quantite, resultat["prix"], resultat["montant"])
    return resultat


def _ecrire(lignes, account_id, creer_positions, index_positions):
    """Inscrit les mouvements retenus, en créant au besoin les positions absentes."""
    from backend.positions import create_position

    importes, touchees = 0, set()
    for ligne in lignes:
        position_id = ligne["position_id"]

        if ligne["sur_ligne"] and not position_id:
            if not creer_positions:
                continue
            cle = _cle(ligne["libelle"])
            connue = index_positions.get(cle)
            if connue:
                position_id = connue["id"]
            else:
                # Quantité et PRU restent à zéro : c'est le journal qui les
                # établira au recalcul, à partir des mouvements importés.
                position_id = create_position(account_id, {
                    "nom": ligne["libelle"][:120], "quantite": 0, "pru": 0,
                    "cours": ligne["prix"], "devise": ligne["devise"],
                    "taux_change": 1.0 if ligne["devise"] == "EUR" else None,
                })
                index_positions[cle] = {"id": position_id, "nom": ligne["libelle"],
                                        "ticker": "", "isin": "", "devise": ligne["devise"]}

        mouvement = {
            "date": ligne["date"], "account_id": account_id, "type": ligne["type"],
            "frais": ligne["frais"], "note": "Importé d'un relevé",
        }
        if ligne["sur_ligne"]:
            mouvement.update({
                "position_id": position_id, "quantite": ligne["quantite"],
                "prix": ligne["prix"], "devise": ligne["devise"],
            })
            touchees.add(position_id)
        else:
            mouvement["montant"] = ligne["montant"]

        add_transaction(mouvement)
        importes += 1

    # `add_transaction` recalcule déjà la position à chaque écriture ; un
    # dernier passage garantit l'ordre chronologique du PMP.
    for position_id in touchees:
        recalc_position(position_id)
    return importes
