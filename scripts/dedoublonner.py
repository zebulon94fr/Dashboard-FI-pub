#!/usr/bin/env python3
"""Repère et retire les doublons de dividendes et de mouvements.

Un même versement saisi à la main puis réimporté depuis un relevé apparaît
deux fois : l'import ne reconnaît un doublon que si la date, le nom et le
montant concordent exactement, et un nom saisi à la main concorde rarement avec
celui d'un courtier.

Le rapprochement se fait donc ici sur la **date et le montant**, le nom servant
seulement à départager. C'est volontairement plus large que la détection de
l'import : c'est un outil de ménage, lancé en connaissance de cause, et il
n'efface rien sans avoir d'abord montré ce qu'il compte effacer.

Usage :
  python scripts/dedoublonner.py                  # liste, n'efface rien
  python scripts/dedoublonner.py --appliquer      # efface les doublons retenus
  python scripts/dedoublonner.py --garder manuel  # garde la saisie manuelle (défaut)
  python scripts/dedoublonner.py --garder importe # garde la ligne importée
"""
import argparse
import collections
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from backend.db import get_db  # noqa: E402

MARQUE_IMPORT = "Importé d'un relevé"


def _groupes(lignes, cle):
    """Groupes de plus d'une ligne partageant la même clé."""
    par_cle = collections.defaultdict(list)
    for ligne in lignes:
        par_cle[cle(ligne)].append(ligne)
    return {k: v for k, v in par_cle.items() if len(v) > 1}


def _a_supprimer(groupe, garder, tous=False):
    """
    Lignes à retirer d'un groupe : celles qui doublent une autre origine.

    Par défaut, seuls les groupes qui mêlent une saisie manuelle et une ligne
    importée sont traités — c'est là qu'est le doublon. Deux lignes importées
    du même relevé ne sont pas un doublon : le courtier a bien déclaré deux
    opérations, et un même titre peut verser deux fois le même jour. Deux
    saisies manuelles sont signalées sans être touchées, faute de savoir
    laquelle était l'erreur. `--tous` lève cette réserve.
    """
    importees = [l for l in groupe if (l["note"] or "") == MARQUE_IMPORT]
    manuelles = [l for l in groupe if (l["note"] or "") != MARQUE_IMPORT]
    if manuelles and importees:
        return importees if garder == "manuel" else manuelles
    return sorted(groupe, key=lambda l: l["id"])[1:] if tous else []


def dividendes(db):
    lignes = [dict(r) for r in db.execute("""
        SELECT d.id, d.date, d.nom, d.montant, d.note, a.nom compte
        FROM dividendes d LEFT JOIN accounts a ON a.id = d.account_id
        ORDER BY d.date, d.id
    """)]
    return _groupes(lignes, lambda l: (l["compte"], l["date"], round(l["montant"], 2)))


def mouvements(db):
    lignes = [dict(r) for r in db.execute("""
        SELECT t.id, t.date, t.nom, t.type, t.quantite, t.prix, t.montant_eur montant,
               t.note, a.nom compte
        FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
        ORDER BY t.date, t.id
    """)]
    return _groupes(lignes, lambda l: (l["compte"], l["date"], l["type"],
                                       round(l["quantite"], 6), round(l["prix"], 6),
                                       round(l["montant"], 2)))


def afficher(titre, groupes, garder, tous):
    if not groupes:
        print(f"{titre} : aucun doublon.")
        return []

    retenues = []
    print(f"\n{titre} : {len(groupes)} groupe(s) de doublons")
    for cle, groupe in sorted(groupes.items()):
        a_retirer = {l["id"] for l in _a_supprimer(groupe, garder, tous)}
        print(f"\n  {cle[0]} — {cle[1]}")
        for ligne in groupe:
            marque = "SUPPRIMÉ" if ligne["id"] in a_retirer else ("gardé   " if a_retirer else "signalé ")
            origine = "importé" if (ligne["note"] or "") == MARQUE_IMPORT else "saisi"
            print(f"    [{marque}] #{ligne['id']:<5} {ligne['nom'][:30]:<30} "
                  f"{ligne['montant']:>10.2f} €  ({origine})")
        retenues.extend(a_retirer)
    return retenues


def main():
    parser = argparse.ArgumentParser(description="Retire les doublons de dividendes et de mouvements.")
    parser.add_argument("--appliquer", action="store_true",
                        help="supprime réellement ; sans cette option, rien n'est effacé")
    parser.add_argument("--garder", choices=("manuel", "importe"), default="manuel",
                        help="laquelle garder quand une saisie manuelle et un import se doublent")
    parser.add_argument("--tous", action="store_true",
                        help="traite aussi les groupes de même origine, normalement laissés intacts")
    parser.add_argument("--dividendes-seulement", action="store_true",
                        help="ne regarde pas le journal des mouvements")
    args = parser.parse_args()

    with get_db() as db:
        div = afficher("Dividendes", dividendes(db), args.garder, args.tous)
        mvt = ([] if args.dividendes_seulement
               else afficher("Mouvements", mouvements(db), args.garder, args.tous))

        total = len(div) + len(mvt)
        if not total:
            print("\nRien à supprimer. Les groupes seulement « signalés » mêlent deux lignes "
                  "de même origine : --tous les traiterait.")
            return
        if not args.appliquer:
            print(f"\n{total} ligne(s) seraient supprimées. "
                  "Relancez avec --appliquer pour le faire.")
            return

        for identifiant in div:
            db.execute("DELETE FROM dividendes WHERE id=?", (identifiant,))
        positions = set()
        for identifiant in mvt:
            ligne = db.execute("SELECT position_id FROM transactions WHERE id=?",
                               (identifiant,)).fetchone()
            if ligne and ligne["position_id"]:
                positions.add(ligne["position_id"])
            db.execute("DELETE FROM transactions WHERE id=?", (identifiant,))

    # Le journal fait la quantité et le prix de revient : retirer un mouvement
    # oblige à les refaire, hors de la transaction SQL ci-dessus.
    if mvt:
        from backend.transactions import recalc_position
        for position_id in positions:
            recalc_position(position_id)

    print(f"\n{total} ligne(s) supprimée(s)"
          + (f", {len(positions)} position(s) recalculée(s)." if positions else "."))


if __name__ == "__main__":
    main()
