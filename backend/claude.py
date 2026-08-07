"""Appel à l'API Anthropic (messages), partagé entre le proxy /api/claude et le résumé Telegram."""
import json
import urllib.request

from backend.settings import load_settings


def call_claude(payload):
    """payload : dict de paramètres de l'API Messages Anthropic (model, messages, etc.).
    Utilise `payload['apiKey']` si fourni, sinon la clé configurée dans settings.json."""
    payload = dict(payload)
    api_key = payload.pop("apiKey", "") or load_settings().get("anthropicKey", "")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())
