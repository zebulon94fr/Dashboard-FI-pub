"""Résumé périodique du portefeuille envoyé sur Telegram, avec analyse IA optionnelle."""
import json
import urllib.request

from backend.claude import call_claude, texte_des_blocs
from backend.rapport import rapport_mensuel
from backend.settings import load_settings
from backend.stats import get_stats


def _fmt_eur(v):
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}{v * 100:.2f}%"


def build_summary_text(stats):
    courant = stats.get("current") or {}
    total = courant.get("total") or 0
    investi = courant.get("investi") or 0
    pv_latent = courant.get("pv_latent_total") or 0
    perf = (pv_latent / investi) if investi else 0

    lignes = [
        "📊 Résumé du portefeuille",
        "",
        f"💰 Total : {_fmt_eur(total)}",
        f"📈 Performance globale : {_fmt_pct(perf)} ({_fmt_eur(pv_latent)})",
    ]
    if stats.get("var24h") is not None:
        lignes.append(f"📅 Variation 24 h : {_fmt_eur(stats['var24h'])} ({_fmt_pct(stats.get('var24h_pct'))})")

    comptes = [c for c in (stats.get("par_compte") or []) if c.get("valorisation")]
    if comptes:
        largeur = max(len(c["nom"]) for c in comptes)
        lignes += ["", "Répartition par compte :"]
        for c in comptes:
            lignes.append(f"  {c['nom']:<{largeur}}  {_fmt_eur(c['valorisation'])}")

    top = [p for p in (stats.get("top_pv") or []) if p.get("pv_pct") is not None][:3]
    if top:
        lignes += ["", "🏆 Meilleures performances :"]
        lignes += [f"  {p['nom']}  {_fmt_pct(p['pv_pct'])}" for p in top]

    pires = [p for p in (stats.get("worst_pv") or []) if p.get("pv_pct") is not None][:3]
    if pires:
        lignes += ["", "⚠️ Moins bonnes performances :"]
        lignes += [f"  {p['nom']}  {_fmt_pct(p['pv_pct'])}" for p in pires]

    return "\n".join(lignes)


def generate_ai_commentary(stats):
    """Court commentaire IA, ou None si aucune clé n'est configurée (dégradation propre)."""
    if not load_settings().get("anthropicKey"):
        return None

    prompt = (
        "Voici les statistiques d'un portefeuille d'investissement français au format JSON. "
        "Rédige un commentaire très concis (3-4 phrases maximum, adapté à un message Telegram) "
        "en français sur la performance de la période et un point d'attention éventuel.\n\n"
        f"{json.dumps(stats, ensure_ascii=False, default=str)}"
    )
    try:
        resultat = call_claude({
            "model": "claude-sonnet-5",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
            "system": "Tu es un conseiller financier expert des marchés et de la fiscalité française. "
                      "Réponds de façon concise et actionnable.",
        })
        return texte_des_blocs(resultat) or None
    except Exception:
        return None


def send_telegram_message(text):
    settings = load_settings()
    token = settings.get("telegramBotToken")
    chat_id = settings.get("telegramChatId")
    if not token or not chat_id:
        raise RuntimeError("Telegram non configuré — lancez scripts/set_telegram.py")

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resultat = json.loads(resp.read())
    if not resultat.get("ok"):
        raise RuntimeError(f"Erreur Telegram : {resultat}")


def send_weekly_summary():
    stats = get_stats()
    if not (stats.get("current") or {}).get("nb_comptes"):
        raise RuntimeError("Aucun compte créé — rien à résumer.")
    texte = build_summary_text(stats)
    commentaire = generate_ai_commentary(stats)
    if commentaire:
        texte += "\n\n🤖 Analyse IA :\n" + commentaire
    send_telegram_message(texte)


def build_monthly_text(rapport):
    """
    Résumé Telegram du mois : la décomposition d'abord, le détail ensuite.

    Le message tient dans une notification. Il ne reprend pas le rapport, il
    donne la réponse — ce que le mois doit au marché et ce qu'il doit à
    l'épargne — et laisse la page HTML porter le reste.
    """
    patrimoine = rapport.get("patrimoine")
    lignes = [f"📅 Rapport de {rapport['libelle']}", ""]

    if not patrimoine:
        lignes.append(rapport.get("message") or "Aucune donnée pour ce mois.")
        return "\n".join(lignes)

    lignes += [
        f"💰 Patrimoine : {_fmt_eur(patrimoine['valeur_fin'])}",
        f"📊 Variation du mois : {_fmt_eur(patrimoine['variation'])}",
        f"   dont mouvements : {_fmt_eur(patrimoine['flux_net'])}",
        f"   dont marché     : {_fmt_eur(patrimoine['gain_marche'])}",
        f"📈 Performance : {_fmt_pct(patrimoine['performance'])} (hors mouvements)",
    ]

    mouvements = rapport.get("mouvements") or []
    if mouvements:
        lignes += ["", "Mouvements :"]
        largeur = max(len(m["label"]) for m in mouvements)
        for m in mouvements:
            lignes.append(f"  {m['icone']} {m['label']:<{largeur}}  "
                          f"{m['nb']:>2} · {_fmt_eur(m['montant'])}")

    dividendes = rapport.get("dividendes") or {}
    if dividendes.get("total"):
        lignes += ["", f"💵 Dividendes du mois : {_fmt_eur(dividendes['total'])}"
                       f" (cumul {_fmt_eur(dividendes['cumul_annee'])})"]

    allocation = rapport.get("allocation") or {}
    if allocation.get("nb_signales"):
        derives = [c for c in allocation["classes"] if c["signale"]]
        lignes += ["", "⚖️ Allocation à surveiller :"]
        for classe in derives:
            signe = "+" if classe["ecart_pts"] > 0 else ""
            lignes.append(f"  {classe['label']} : {classe['poids_pct']:.1f} % "
                          f"pour {classe['cible_pct']:.0f} % visés "
                          f"({signe}{classe['ecart_pts']:.1f} pts)")

    return "\n".join(lignes)


def send_monthly_report(mois=None):
    """
    Envoie le rapport du mois écoulé. Sans `mois`, le mois précédent.

    L'analyse IA n'est pas rejouée ici : le résumé hebdomadaire en porte une,
    et un commentaire mensuel écrit sur les mêmes chiffres n'ajouterait qu'une
    paraphrase. Le rapport, lui, apporte des chiffres que l'hebdomadaire n'a pas.
    """
    rapport = rapport_mensuel(mois)
    send_telegram_message(build_monthly_text(rapport))
    return rapport["mois"]
