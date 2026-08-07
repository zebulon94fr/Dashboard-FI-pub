#!/usr/bin/env python3
"""Configure (ou désactive) l'authentification HTTP Basic du dashboard.

Le mot de passe est saisi en local (invisible, jamais transmis ailleurs) et
seul son hash est écrit dans settings.json — comme pour la clé API Anthropic,
ce fichier est gitignored et reste sur la machine.

Usage :
  python scripts/set_password.py            # configure/modifie l'authentification
  python scripts/set_password.py --disable  # supprime l'authentification (accès libre)
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.settings import load_settings, save_settings  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def disable():
    s = load_settings()
    s.pop("authUsername", None)
    s.pop("authPasswordHash", None)
    save_settings(s)
    print("Authentification désactivée — le dashboard est de nouveau accessible sans identifiants.")


def configure():
    username = input("Nom d'utilisateur : ").strip()
    if not username:
        print("Nom d'utilisateur requis, abandon.")
        sys.exit(1)

    password = getpass.getpass("Mot de passe : ")
    if not password:
        print("Mot de passe requis, abandon.")
        sys.exit(1)
    confirm = getpass.getpass("Confirmer le mot de passe : ")
    if password != confirm:
        print("Les mots de passe ne correspondent pas, abandon.")
        sys.exit(1)

    s = load_settings()
    s["authUsername"] = username
    # pbkdf2:sha256 plutôt que le défaut "scrypt" : scrypt nécessite hashlib compilé
    # contre OpenSSL, absent sur certains environnements (ex. LibreSSL sur macOS).
    s["authPasswordHash"] = generate_password_hash(password, method="pbkdf2:sha256")
    save_settings(s)
    print(f"Authentification activée pour l'utilisateur « {username} ».")
    print("Redémarrez le serveur pour appliquer le changement.")


if __name__ == "__main__":
    if "--disable" in sys.argv:
        disable()
    else:
        configure()
