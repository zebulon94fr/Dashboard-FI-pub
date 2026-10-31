"""Appel à l'API Anthropic (messages), partagé entre le proxy /api/claude et le résumé Telegram."""
import json
import urllib.error
import urllib.request

from backend.settings import load_settings

URL = "https://api.anthropic.com/v1/messages"
VERSION_API = "2023-06-01"


class ClaudeError(RuntimeError):
    """Erreur de l'API Anthropic, avec le message qu'elle a réellement renvoyé."""


def _message_erreur(erreur):
    """
    Message d'origine porté par le corps de la réponse d'erreur.

    `str(HTTPError)` ne donne que « HTTP Error 400: Bad Request », là où le
    corps dit ce qui ne va pas : « invalid x-api-key », « model not found »,
    « credit balance is too low ». Sans lui, l'utilisateur voit un code et ne
    peut rien en faire.
    """
    try:
        corps = json.loads(erreur.read())
    except Exception:
        return ""
    detail = corps.get("error")
    if isinstance(detail, dict):
        return detail.get("message") or detail.get("type") or ""
    return str(detail or "")


def texte_des_blocs(reponse):
    """
    Texte d'une réponse de l'API, blocs de texte seulement.

    Une réponse peut contenir des blocs qui n'en sont pas — un raisonnement,
    un appel d'outil. Les parcourir en lisant `text` donnerait une chaîne vide
    sans qu'on sache pourquoi : on ne retient donc que les blocs de texte, et
    l'appelant peut constater qu'il n'y en avait aucun.
    """
    blocs = (reponse or {}).get("content")
    if not isinstance(blocs, list):
        return ""
    return "".join(bloc.get("text", "") for bloc in blocs
                   if isinstance(bloc, dict) and bloc.get("type") == "text").strip()


def call_claude(payload):
    """payload : dict de paramètres de l'API Messages Anthropic (model, messages, etc.).
    Utilise `payload['apiKey']` si fourni, sinon la clé configurée dans settings.json."""
    payload = dict(payload)
    api_key = payload.pop("apiKey", "") or load_settings().get("anthropicKey", "")
    if not api_key:
        raise ClaudeError(
            "Aucune clé API Anthropic : renseignez-la dans l'onglet Arbitrage IA, "
            "ou configurez-la une fois pour toutes dans settings.json."
        )

    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": VERSION_API,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = _message_erreur(e)
        raise ClaudeError(
            f"L'API Anthropic a répondu {e.code}"
            + (f" : {detail}" if detail else f" ({e.reason}).")
        ) from None
    except urllib.error.URLError as e:
        raise ClaudeError(
            f"API Anthropic injoignable : {e.reason}. "
            "Vérifiez que le serveur a accès à Internet."
        ) from None
