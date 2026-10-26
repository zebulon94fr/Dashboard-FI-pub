"""Mise en page du rapport mensuel : une page autonome, lisible et imprimable.

Autonome au sens strict — ni JavaScript, ni feuille de style extérieure, ni
police distante. Un rapport se garde, s'imprime et se transfère ; il doit
rester lisible dans cinq ans, et dans un client de messagerie qui n'exécute
rien. La courbe du mois est donc un SVG écrit à la main plutôt qu'un graphique
calculé dans le navigateur.
"""
import datetime
import html

from backend.rapport import ECART_SIGNALE_PTS, SANS_LIMITE, libelle
from catalog import TYPES_TRANSACTION

# Teintes reprises du dashboard, avec un équivalent clair pour l'impression.
# Le signe d'un montant est porté par la couleur ET par le signe lui-même :
# une page imprimée en noir et blanc doit rester juste.
STYLE = """
:root{
  --encre:#1f2328; --discret:#656d76; --fond:#ffffff; --surface:#f6f8fa;
  --trait:#d0d7de; --vert:#1a7f37; --rouge:#cf222e; --accent:#0969da; --ambre:#9a6700;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --encre:#e6edf3; --discret:#8b949e; --fond:#0d1117; --surface:#161b22;
    --trait:#30363d; --vert:#3fb950; --rouge:#f85149; --accent:#58a6ff; --ambre:#d29922;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--fond);color:var(--encre);line-height:1.6;font-size:15px;
  -webkit-text-size-adjust:100%}
.page{max-width:860px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;line-height:1.25;margin-bottom:4px}
h2{font-size:16px;margin:32px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--trait)}
.sous-titre{color:var(--discret);font-size:13px;margin-bottom:24px}
.phrase{font-size:17px;line-height:1.55;margin-bottom:20px}
.pos{color:var(--vert)}.neg{color:var(--rouge)}.neu{color:var(--discret)}
.nb{font-variant-numeric:tabular-nums;white-space:nowrap}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:8px}
.carte{background:var(--surface);border:1px solid var(--trait);border-radius:10px;padding:14px}
.carte-label{font-size:11px;color:var(--discret);text-transform:uppercase;letter-spacing:.5px}
.carte-valeur{font-size:22px;font-weight:600;margin-top:4px}
.carte-sous{font-size:12px;color:var(--discret);margin-top:2px}
/* Cinq colonnes de montants ne tiennent pas dans la largeur d'un téléphone.
   Plutôt que de retirer une colonne, le tableau défile dans son cadre : la
   page, elle, ne défile jamais latéralement. */
.tableau{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:420px}
th{text-align:left;font-size:11px;color:var(--discret);text-transform:uppercase;
  letter-spacing:.5px;font-weight:500;padding:6px 8px;border-bottom:1px solid var(--trait)}
td{padding:6px 8px;border-bottom:1px solid var(--trait)}
td.droite,th.droite{text-align:right}
tfoot td{font-weight:600;background:var(--surface)}
.jauge{display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--trait);
  vertical-align:middle;position:relative}
.jauge>.reel{display:block;height:100%;border-radius:4px}
/* Trait de la cible : sans lui la jauge ne dit que le poids réel, et l'écart
   qu'elle est censée illustrer reste à lire dans la colonne voisine. */
.jauge>.cible{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--encre);
  border-radius:1px}
.note{font-size:12.5px;color:var(--discret);margin-top:10px;line-height:1.6}
.alerte{border-left:3px solid var(--ambre);background:var(--surface);padding:10px 14px;
  border-radius:0 6px 6px 0;font-size:13px;color:var(--discret);margin:14px 0}
.vide{color:var(--discret);font-size:13.5px;padding:10px 0}
.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:40px;
  padding-top:14px;border-top:1px solid var(--trait)}
.nav a{color:var(--accent);text-decoration:none}
.nav a:hover{text-decoration:underline}
.nav .courant{color:var(--encre);font-weight:600}
.courbe{width:100%;height:120px;display:block;margin:4px 0 2px}
@media print{
  .tableau{overflow:visible}
  table{min-width:0}
  body{background:#fff;color:#000;font-size:11.5pt}
  .nav{display:none}
  h2{page-break-after:avoid}
  table{page-break-inside:avoid}
}
"""


def _eur(valeur, signe=False):
    if valeur is None:
        return "—"
    texte = f"{valeur:,.2f}".replace(",", " ").replace(".", ",")
    if signe and valeur > 0:
        texte = "+" + texte
    return texte + " €"


def _pct(valeur, decimales=2, signe=True):
    if valeur is None:
        return "—"
    brut = f"{valeur * 100:.{decimales}f}".replace(".", ",")
    return (("+" if valeur > 0 and signe else "") + brut + " %")


def _pts(valeur):
    if valeur is None:
        return "—"
    return ("+" if valeur > 0 else "") + f"{valeur:.1f}".replace(".", ",") + " pts"


def _label_type(type_id):
    return TYPES_TRANSACTION.get(type_id, {}).get("label", type_id)


def _classe(valeur, passif=False):
    """
    Couleur d'un montant signé. Sur un compte de passif, les signes s'inversent :
    un capital restant dû qui grossit est une mauvaise nouvelle, et l'afficher
    en vert parce qu'il monte serait le contraire de ce qu'il faut lire.
    """
    if valeur is None or valeur == 0:
        return "neu"
    bon = valeur < 0 if passif else valeur > 0
    return "pos" if bon else "neg"


def _jour(iso):
    """« 14 oct. » — assez pour situer une opération dans son mois."""
    abreges = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
               "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    try:
        date = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return html.escape(str(iso))
    # « 1er » en lettres ordinaires : les exposants Unicode se rendent mal
    # selon la police et se lisent mal à voix haute.
    jour = "1er" if date.day == 1 else str(date.day)
    return f"{jour} {abreges[date.month - 1]}"


def _periode(rapport):
    """
    Période réellement couverte, et non les bornes du mois.

    Une période qui court encore s'arrête au dernier jour connu, et une fenêtre
    glissante peut commencer avant le premier jour connu. Afficher ses bornes
    théoriques laisserait croire à une période complète, et sa variation se
    comparerait à tort à celle d'une période pleine.
    """
    debut = rapport.get("debut_couvert") or rapport["debut"]
    fin = rapport.get("fin_couverte") or rapport["fin"]
    periode = f"Du {_jour(debut)} au {_jour(fin)}"
    # La mention ne vaut que pour un mois : une fenêtre glissante s'arrête à
    # aujourd'hui par construction, le dire n'apprendrait rien.
    if rapport.get("en_cours") and rapport.get("mois"):
        periode += " — <strong>mois en cours</strong>"
    return f"{periode} · établi le {_jour(rapport['genere_le'])}"


def _voisins(mois):
    """Mois précédent et suivant, pour la navigation en pied de page."""
    annee, numero = (int(p) for p in mois.split("-")[:2])
    avant = (annee - 1, 12) if numero == 1 else (annee, numero - 1)
    apres = (annee + 1, 1) if numero == 12 else (annee, numero + 1)
    return f"{avant[0]:04d}-{avant[1]:02d}", f"{apres[0]:04d}-{apres[1]:02d}"


# ══════════════════════════════════════════════════════════════
# COURBE DU MOIS
# ══════════════════════════════════════════════════════════════
def _courbe(serie, jours_flux):
    """
    Courbe du patrimoine sur le mois, en SVG, sans dépendance.

    Les journées portant un versement ou un retrait sont marquées : c'est là
    que la courbe monte sans que le marché y soit pour quelque chose, et le
    lecteur doit pouvoir le voir sur le dessin comme il le lit dans le tableau.
    """
    if len(serie) < 2:
        return ""

    largeur, hauteur, marge = 820, 120, 10
    valeurs = [point["valorisation"] for point in serie]
    bas, haut = min(valeurs), max(valeurs)
    amplitude = (haut - bas) or (haut or 1)
    # Une marge verticale de 8 % évite que le sommet et le creux ne touchent
    # les bords, où ils se confondraient avec le cadre.
    bas -= amplitude * 0.08
    haut += amplitude * 0.08
    etendue = haut - bas

    pas = (largeur - 2 * marge) / (len(serie) - 1)
    points = [(marge + i * pas,
               hauteur - marge - (valeur - bas) / etendue * (hauteur - 2 * marge))
              for i, valeur in enumerate(valeurs)]

    ligne = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    aire = (f"{points[0][0]:.1f},{hauteur - marge} " + ligne
            + f" {points[-1][0]:.1f},{hauteur - marge}")

    flux = set(jours_flux or ())
    marques = "".join(
        f'<circle cx="{points[i][0]:.1f}" cy="{points[i][1]:.1f}" r="3.5" '
        f'fill="var(--fond)" stroke="var(--ambre)" stroke-width="2"><title>'
        f'{html.escape(_jour(point["date"]))} — versement ou retrait ce jour-là</title></circle>'
        for i, point in enumerate(serie) if point["date"] in flux
    )

    hausse = valeurs[-1] >= valeurs[0]
    teinte = "var(--vert)" if hausse else "var(--rouge)"

    return f"""
    <svg class="courbe" viewBox="0 0 {largeur} {hauteur}" preserveAspectRatio="none"
         role="img" aria-label="Patrimoine jour par jour sur le mois, de {_eur(valeurs[0])} à {_eur(valeurs[-1])}">
      <polygon points="{aire}" fill="{teinte}" opacity="0.10"/>
      <polyline points="{ligne}" fill="none" stroke="{teinte}" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round"/>
      {marques}
    </svg>
    <div class="note">
      Le patrimoine jour par jour, versements compris — c'est bien la courbe de ce que vous
      avez eu. Les cercles marquent les journées portant un mouvement : la courbe y monte ou
      y descend sans que le marché y soit pour quelque chose.
    </div>"""


# ══════════════════════════════════════════════════════════════
# SECTIONS
# ══════════════════════════════════════════════════════════════
def _entete(rapport):
    patrimoine = rapport["patrimoine"]
    if not patrimoine:
        return f'<div class="alerte">{html.escape(rapport["message"] or "Mois sans données.")}</div>'

    variation = patrimoine["variation"]
    flux_net = patrimoine["flux_net"]
    gain = patrimoine["gain_marche"]

    # La phrase d'ouverture dit la seule chose qui compte à cette échéance :
    # ce que le mois doit au marché, et ce qu'il doit à l'épargne.
    if abs(flux_net) < 1:
        phrase = (f"Le patrimoine a {'progressé' if variation >= 0 else 'reculé'} de "
                  f"<strong class=\"{_classe(variation)}\">{_eur(abs(variation))}</strong>, "
                  "sans aucun mouvement enregistré : c'est du marché, tout entier.")
    else:
        phrase = (f"Le patrimoine a {'progressé' if variation >= 0 else 'reculé'} de "
                  f"<strong class=\"{_classe(variation)}\">{_eur(abs(variation))}</strong>, "
                  f"dont <strong>{_eur(flux_net, signe=True)}</strong> de mouvements et "
                  f"<strong class=\"{_classe(gain)}\">{_eur(gain, signe=True)}</strong> "
                  "venus du marché.")

    return f"""
    <p class="phrase">{phrase}</p>
    <div class="cartes">
      <div class="carte">
        <div class="carte-label">Patrimoine au {_jour(patrimoine["date_fin"])}</div>
        <div class="carte-valeur nb">{_eur(patrimoine["valeur_fin"])}</div>
        <div class="carte-sous">contre {_eur(patrimoine["valeur_debut"])} au départ</div>
      </div>
      <div class="carte">
        <div class="carte-label">Variation du mois</div>
        <div class="carte-valeur nb {_classe(variation)}">{_eur(variation, signe=True)}</div>
        <div class="carte-sous">versements et retraits compris</div>
      </div>
      <div class="carte">
        <div class="carte-label">Gain de marché</div>
        <div class="carte-valeur nb {_classe(gain)}">{_eur(gain, signe=True)}</div>
        <div class="carte-sous">hors mouvements</div>
      </div>
      <div class="carte">
        <div class="carte-label">Performance du mois</div>
        <div class="carte-valeur nb {_classe(patrimoine["performance"])}">{_pct(patrimoine["performance"])}</div>
        <div class="carte-sous">corrigée des mouvements</div>
      </div>
    </div>
    <div class="note">
      « Mouvements » compte tout ce qui entre ou sort du périmètre valorisé : versements et
      retraits, mais aussi achats et ventes, qui font apparaître ou disparaître une ligne, et
      les dividendes encaissés, qui en sortent. C'est la même convention que la performance
      de l'onglet Historique — sans elle, un versement se lirait comme un bon mois de marché.
    </div>
    {_courbe(patrimoine["serie"], patrimoine.get("jours_flux"))}
    {f'<div class="alerte">{html.escape(rapport["message"])}</div>' if rapport["message"] else ''}"""


def _section_mouvements(rapport):
    resume = rapport["mouvements"]
    if not resume:
        return ('<h2>Mouvements</h2>'
                '<div class="vide">Aucun mouvement enregistré ce mois-ci.</div>')

    lignes = "".join(f"""<tr>
        <td>{html.escape(m["icone"])} {html.escape(m["label"])}</td>
        <td class="droite nb">{m["nb"]}</td>
        <td class="droite nb">{_eur(m["montant"])}</td>
      </tr>""" for m in resume)

    detail = rapport["mouvements_detail"]
    lignes_detail = "".join(f"""<tr>
        <td class="nb">{_jour(m["date"])}</td>
        <td>{html.escape(m["nom"] or _label_type(m["type"]))}</td>
        <td>{html.escape(m["compte"])}</td>
        <td>{html.escape(_label_type(m["type"]))}</td>
        <td class="droite nb">{_eur(m["montant_eur"])}</td>
      </tr>""" for m in detail)

    return f"""
    <h2>Mouvements</h2>
    <div class="tableau"><table>
      <thead><tr><th>Type</th><th class="droite">Nombre</th><th class="droite">Montant</th></tr></thead>
      <tbody>{lignes}</tbody>
    </table></div>
    <h2>Le détail</h2>
    <div class="tableau"><table>
      <thead><tr><th>Date</th><th>Ligne</th><th>Compte</th><th>Type</th>
        <th class="droite">Montant</th></tr></thead>
      <tbody>{lignes_detail}</tbody>
    </table></div>
    <div class="note">
      Les montants sont toujours positifs : c'est le type qui porte le sens du flux.
    </div>"""


def _section_dividendes(rapport):
    dividendes = rapport["dividendes"]
    if not dividendes["lignes"]:
        return (f'<h2>Dividendes</h2><div class="vide">Aucun dividende encaissé ce mois-ci. '
                f'Cumul depuis le 1<sup>er</sup> janvier : {_eur(dividendes["cumul_annee"])}.</div>')

    lignes = "".join(f"""<tr>
        <td class="nb">{_jour(d["date"])}</td>
        <td>{html.escape(d["nom"])}</td>
        <td>{html.escape(d["compte"])}</td>
        <td class="droite nb">{_eur(d["montant"])}</td>
      </tr>""" for d in dividendes["lignes"])

    return f"""
    <h2>Dividendes</h2>
    <div class="tableau"><table>
      <thead><tr><th>Date</th><th>Ligne</th><th>Compte</th><th class="droite">Brut</th></tr></thead>
      <tbody>{lignes}</tbody>
      <tfoot><tr><td colspan="3">Total du mois</td>
        <td class="droite nb">{_eur(dividendes["total"])}</td></tr></tfoot>
    </table></div>
    <div class="note">Cumul depuis le 1<sup>er</sup> janvier : {_eur(dividendes["cumul_annee"])}.</div>"""


def _section_comptes(rapport):
    comptes = rapport["comptes"]
    if not comptes:
        return ""

    lignes = "".join(f"""<tr>
        <td>{html.escape(c["nom"])}{' <span class="neu">(passif)</span>' if c["passif"] else ''}</td>
        <td class="droite nb">{_eur(c["valeur_fin"])}</td>
        <td class="droite nb {_classe(c["variation"], c["passif"])}">{_eur(c["variation"], signe=True)}</td>
        <td class="droite nb">{_eur(c["flux_net"], signe=True) if c["flux_net"] else "—"}</td>
        <td class="droite nb {_classe(c["gain_marche"], c["passif"])}">{_eur(c["gain_marche"], signe=True)}</td>
      </tr>""" for c in comptes)

    return f"""
    <h2>Compte par compte</h2>
    <div class="tableau"><table>
      <thead><tr><th>Compte</th><th class="droite">Fin de mois</th>
        <th class="droite">Variation</th><th class="droite">Mouvements</th>
        <th class="droite">Gain de marché</th></tr></thead>
      <tbody>{lignes}</tbody>
    </table></div>
    <div class="note">
      Variation = mouvements + gain de marché, compte par compte comme pour l'ensemble.
      Un compte de passif porte son capital restant dû : il baisse quand vous remboursez, et
      ses signes se lisent donc à l'envers — c'est ce que fait la couleur.
    </div>"""


def _section_allocation(rapport):
    allocation = rapport["allocation"]
    if not allocation["cibles_definies"]:
        return ('<h2>Allocation</h2><div class="vide">Aucune allocation cible définie — '
                'l\'onglet Rebalancing du dashboard permet de la renseigner.</div>')

    def ligne(classe):
        part = min(100.0, max(0.0, classe["poids_pct"]))
        return f"""<tr>
          <td>{html.escape(classe["label"])}</td>
          <td class="droite nb">{_pct(classe["poids_pct"] / 100, 1, signe=False)}</td>
          <td class="droite nb">{_pct(classe["cible_pct"] / 100, 1, signe=False)}</td>
          <td class="droite nb {'neg' if classe["signale"] else 'neu'}">{_pts(classe["ecart_pts"])}</td>
          <td><span class="jauge" title="Réel {part:.1f} %, cible {classe["cible_pct"]:.0f} %"
            ><span class="reel" style="width:{part:.1f}%;background:{classe["couleur"]}"></span
            ><span class="cible" style="left:{min(99.0, max(0.0, classe["cible_pct"])):.1f}%"></span></span></td>
        </tr>"""

    signales = allocation["nb_signales"]
    return f"""
    <h2>Allocation</h2>
    <div class="tableau"><table>
      <thead><tr><th>Classe d'actifs</th><th class="droite">Réel</th><th class="droite">Cible</th>
        <th class="droite">Écart</th><th>Réel ┃ cible</th></tr></thead>
      <tbody>{"".join(ligne(c) for c in allocation["classes"])}</tbody>
    </table></div>
    <div class="note">
      Mesurée au {_jour(rapport["genere_le"])}, jour du rapport, et non à la fin du mois :
      une répartition par classe se reconstitue depuis les positions du moment, qui n'en
      gardent pas la mémoire.
      {f"{signales} classe(s) s'écartent de plus de {ECART_SIGNALE_PTS:.0f} points de leur cible — "
       "l'onglet Rebalancing propose les ordres correspondants."
       if signales else "Aucune classe ne s'écarte de plus de "
       f"{ECART_SIGNALE_PTS:.0f} points de sa cible."}
    </div>"""


# ══════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════
# Périodes proposées en pied de page d'un rapport glissant : les mêmes que
# celles de l'onglet Historique, pour qu'on retrouve ce qu'on y a choisi.
PERIODES = (30, 90, 180, 365, SANS_LIMITE)


def _navigation(rapport, base_url):
    """
    Pied de page : les mois voisins pour un rapport mensuel, les autres
    fenêtres pour un rapport glissant. Dans les deux cas, la page reste
    parcourable sans revenir au dashboard.
    """
    if rapport.get("mois"):
        avant, apres = _voisins(rapport["mois"])
        return (f'<a href="{base_url}/rapport/{avant}">← {html.escape(libelle(avant))}</a>'
                f'<a href="{base_url}/rapport/{apres}">{html.escape(libelle(apres))} →</a>')

    courant = rapport.get("jours")
    liens = []
    for jours in PERIODES:
        # Mêmes étiquettes que les boutons de l'onglet Historique, pour qu'on
        # reconnaisse la fenêtre qu'on vient d'y choisir.
        etiquette = "Tout" if jours >= SANS_LIMITE else (
            f"{jours // 365}A" if jours % 365 == 0 else f"{jours // 30}M")
        liens.append(f'<span class="courant">{html.escape(etiquette)}</span>' if jours == courant
                     else f'<a href="{base_url}/rapport?jours={jours}">{html.escape(etiquette)}</a>')
    return "".join(liens)


def page_rapport(rapport, base_url=""):
    """Rapport complet d'une période, en une page HTML autonome."""
    titre = (f"Rapport mensuel — {rapport['libelle']}" if rapport.get("mois")
             else f"Rapport sur {rapport['libelle']}")

    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titre)}</title>
<!-- Icône en ligne : sans elle le navigateur réclame /favicon.ico à chaque
     ouverture et laisse un 404 dans les journaux du serveur. -->
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Ctext y='14' font-size='14'%3E%F0%9F%93%85%3C/text%3E%3C/svg%3E">
<style>{STYLE}</style>
</head>
<body>
<div class="page">
  <h1>{html.escape(titre)}</h1>
  <div class="sous-titre">{_periode(rapport)}</div>
  {_entete(rapport)}
  {_section_comptes(rapport)}
  {_section_allocation(rapport)}
  {_section_mouvements(rapport)}
  {_section_dividendes(rapport)}
  <div class="nav">
    {_navigation(rapport, base_url)}
    <a href="{base_url}/">Retour au dashboard</a>
  </div>
</div>
</body>
</html>"""
