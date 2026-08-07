#!/usr/bin/env python3
"""Configure (ou désactive) l'envoi du résumé hebdomadaire sur Telegram.

Comment obtenir les identifiants :
  1. Dans Telegram, cherchez « @BotFather », envoyez /newbot et suivez les instructions.
     BotFather vous donne un token du type 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.
  2. Envoyez n'importe quel message à votre nouveau bot (pour qu'il « vous connaisse »).
  3. Ouvrez dans un navigateur :
       https://api.telegram.org/bot<TON_TOKEN>/getUpdates
     et repérez "chat":{"id": ...} dans la réponse — c'est votre chat_id.

Usage :
  python scripts/set_telegram.py            # configure/modifie
  python scripts/set_telegram.py --disable  # désactive
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.settings import load_settings, save_settings  # noqa: E402


def disable():
    s = load_settings()
    s.pop("telegramBotToken", None)
    s.pop("telegramChatId", None)
    save_settings(s)
    print("Résumé Telegram désactivé.")


def configure():
    token = input("Bot token (@BotFather) : ").strip()
    if not token:
        print("Token requis, abandon.")
        sys.exit(1)

    chat_id = input("Chat ID : ").strip()
    if not chat_id:
        print("Chat ID requis, abandon.")
        sys.exit(1)

    s = load_settings()
    s["telegramBotToken"] = token
    s["telegramChatId"] = chat_id
    save_settings(s)
    print("Résumé Telegram configuré.")
    print("Testez avec : curl -X POST http://127.0.0.1:8742/api/telegram/send")


if __name__ == "__main__":
    if "--disable" in sys.argv:
        disable()
    else:
        configure()
