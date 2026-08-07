"""Résumé périodique du portefeuille envoyé sur Telegram, avec analyse IA optionnelle."""
import json
import urllib.request

from backend.claude import call_claude
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
        texte = "".join(bloc.get("text", "") for bloc in resultat.get("content", []))
        return texte.strip() or None
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
