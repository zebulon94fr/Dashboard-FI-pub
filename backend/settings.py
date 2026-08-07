"""Lecture/écriture de settings.json (clé API Anthropic)."""
import json
import os
import shutil

import config


def load_settings():
    if not os.path.exists(config.SETTINGS_FILE):
        return {}
    with open(config.SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_settings(s):
    tmp = config.SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    shutil.move(tmp, config.SETTINGS_FILE)
