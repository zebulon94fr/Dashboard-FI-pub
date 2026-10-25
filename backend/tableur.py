"""Lecture d'un classeur .xlsx, sans dépendance extérieure.

Un classeur Excel est un zip de fichiers XML : la bibliothèque standard suffit
à l'ouvrir, et une dépendance de moins est une dépendance de moins à tenir à
jour sur un serveur auto-hébergé.

Deux pièges justifient ce module plutôt qu'une poignée de lignes :

  * une **date** y est un nombre — 46310 pour le 2 octobre 2026 — et seul le
    style de la cellule dit qu'il s'agit d'une date plutôt que d'un montant ;
  * les cellules **vides sont absentes** du XML. Une ligne n'est donc pas une
    suite de valeurs : chacune porte sa coordonnée (« D7 »), et c'est à la
    lecture de rétablir les trous, sans quoi les colonnes se décalent.
"""
import datetime
import io
import re
import xml.etree.ElementTree as ET
import zipfile

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# Excel compte les jours depuis le 1er janvier 1900, en considérant à tort 1900
# comme bissextile : l'origine effective est donc le 30 décembre 1899.
ORIGINE = datetime.date(1899, 12, 30)

# Formats de nombre réservés aux dates par la spécification. Au-delà de 163,
# les formats sont définis par le classeur et s'examinent un par un.
FORMATS_DATE = frozenset(range(14, 23)) | frozenset(range(27, 37)) | frozenset(range(45, 48)) \
    | frozenset(range(50, 59))

SIGNATURE_ZIP = b"PK\x03\x04"


class TableurError(ValueError):
    """Classeur illisible — message destiné à l'utilisateur."""


def est_classeur(donnees):
    """Vrai si ces octets sont un classeur (ou tout autre zip)."""
    return isinstance(donnees, (bytes, bytearray)) and bytes(donnees[:4]) == SIGNATURE_ZIP


def _index_colonne(reference):
    """« D7 » -> 3. Les colonnes se comptent en base 26, de A à Z puis AA."""
    lettres = re.match(r"[A-Z]+", reference or "A").group(0)
    index = 0
    for lettre in lettres:
        index = index * 26 + (ord(lettre) - 64)
    return index - 1


def _styles_dates(archive):
    """Indices de style qui désignent une date, d'après les formats du classeur."""
    if "xl/styles.xml" not in archive.namelist():
        return set()
    racine = ET.fromstring(archive.read("xl/styles.xml"))

    personnalises = set()
    for fmt in racine.iter(f"{NS}numFmt"):
        code = (fmt.get("formatCode") or "").lower()
        # Un format de date porte des jours, des mois ou des années ; le crochet
        # d'une durée ([h]:mm) n'en fait pas une date.
        if re.search(r"[dmy]", re.sub(r"\[[^\]]*\]|\"[^\"]*\"", "", code)):
            personnalises.add(int(fmt.get("numFmtId")))

    styles = set()
    cellules = racine.find(f"{NS}cellXfs")
    for index, xf in enumerate(cellules.findall(f"{NS}xf") if cellules is not None else []):
        identifiant = int(xf.get("numFmtId") or 0)
        if identifiant in FORMATS_DATE or identifiant in personnalises:
            styles.add(index)
    return styles


def _chaines_partagees(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    racine = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{NS}t"))
            for si in racine.findall(f"{NS}si")]


def _premiere_feuille(archive):
    noms = [n for n in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
    if not noms:
        raise TableurError("Ce classeur ne contient aucune feuille de calcul.")
    return sorted(noms, key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()))[0]


def _serie_en_date(valeur):
    """Numéro de série Excel converti en date ISO, ou None s'il n'en est pas un."""
    try:
        jours = int(float(valeur))
    except (TypeError, ValueError):
        return None
    # Bornes larges mais finies : en deçà de 1, Excel ne date rien ; au-delà de
    # 2958465, on dépasse le 31 décembre 9999 que la bibliothèque sait écrire.
    if not 1 <= jours <= 2958465:
        return None
    return (ORIGINE + datetime.timedelta(days=jours)).isoformat()


def lire_xlsx(donnees, maximum_lignes=20000):
    """
    (en-têtes, lignes) de la première feuille, toutes valeurs en texte.

    Les dates sont rendues au format AAAA-MM-JJ, les nombres tels qu'Excel les
    a stockés — point décimal — et les cellules absentes comme des chaînes
    vides, à leur place.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(donnees) if isinstance(donnees, (bytes, bytearray))
                                  else donnees)
    except zipfile.BadZipFile:
        raise TableurError("Fichier illisible : ce n'est pas un classeur .xlsx valide.")

    with archive:
        partagees = _chaines_partagees(archive)
        styles_dates = _styles_dates(archive)
        racine = ET.fromstring(archive.read(_premiere_feuille(archive)))

        lignes = []
        for row in racine.iter(f"{NS}row"):
            cellules = {}
            for c in row.findall(f"{NS}c"):
                index = _index_colonne(c.get("r"))
                type_cellule = c.get("t")
                if type_cellule == "inlineStr":
                    texte = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                else:
                    valeur = c.find(f"{NS}v")
                    texte = "" if valeur is None else (valeur.text or "")
                    if type_cellule == "s" and texte.isdigit():
                        texte = partagees[int(texte)] if int(texte) < len(partagees) else ""
                    elif type_cellule == "b":
                        texte = "VRAI" if texte == "1" else "FAUX"
                    elif not type_cellule or type_cellule == "n":
                        style = int(c.get("s") or 0)
                        if style in styles_dates:
                            texte = _serie_en_date(texte) or texte
                cellules[index] = texte
            if cellules:
                largeur = max(cellules) + 1
                lignes.append([cellules.get(i, "") for i in range(largeur)])
            if len(lignes) > maximum_lignes:
                raise TableurError(
                    f"Classeur trop volumineux : plus de {maximum_lignes} lignes. "
                    "Découpez-le par année."
                )

    lignes = [l for l in lignes if any((c or "").strip() for c in l)]
    if len(lignes) < 2:
        raise TableurError(
            "La feuille ne contient qu'une ligne : il faut un en-tête et au moins un mouvement."
        )

    entetes = [str(c).strip() for c in lignes[0]]
    largeur = len(entetes)
    corps = [(l + [""] * largeur)[:largeur] for l in lignes[1:]]
    return entetes, corps
