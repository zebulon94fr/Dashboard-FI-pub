#!/usr/bin/env python3
"""Sauvegarde la base et purge les sauvegardes trop anciennes.

Utilise l'API `Connection.backup()` de la bibliothèque standard : le snapshot est
cohérent même si le serveur écrit pendant la copie, et même en mode WAL. Aucune
dépendance externe — surtout pas le binaire `sqlite3`, absent d'une Debian minimale.

Appelé par deploy/dashboard-fi-backup.service, ou à la main :
  python3 scripts/backup_db.py
  DASHBOARD_BACKUP_RETENTION_DAYS=30 python3 scripts/backup_db.py
"""
import datetime
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402

RETENTION_DEFAUT = 14


def sauvegarder(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Restes d'une exécution interrompue : ils fausseraient la copie.
    for suffixe in ("", "-wal", "-shm"):
        Path(str(destination) + suffixe).unlink(missing_ok=True)

    # `with sqlite3.connect(...)` valide la transaction mais ne ferme pas la
    # connexion. Sans fermeture explicite, la copie reste dans le journal WAL
    # et le fichier .db obtenu est incomplet.
    origine = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    copie = sqlite3.connect(destination)
    try:
        origine.backup(copie)
    finally:
        copie.close()      # déclenche le checkpoint WAL et retire les fichiers -wal/-shm
        origine.close()


def purger(repertoire: Path, retention_jours: int, sauf: Path):
    limite = datetime.datetime.now() - datetime.timedelta(days=retention_jours)
    supprimees = 0
    for fichier in repertoire.glob("dashboard-*.db"):
        if fichier == sauf:
            continue   # jamais la sauvegarde qui vient d'être écrite
        if datetime.datetime.fromtimestamp(fichier.stat().st_mtime) < limite:
            fichier.unlink()
            supprimees += 1
    return supprimees


def main():
    source = Path(config.DB_FILE)
    if not source.exists():
        print(f"Base introuvable ({source}) — rien à sauvegarder.")
        return

    try:
        retention = int(os.environ.get("DASHBOARD_BACKUP_RETENTION_DAYS", RETENTION_DEFAUT))
    except ValueError:
        retention = RETENTION_DEFAUT

    repertoire = source.parent / "backups"
    destination = repertoire / f"dashboard-{datetime.date.today().isoformat()}.db"

    sauvegarder(source, destination)
    taille = destination.stat().st_size / 1024
    print(f"Sauvegarde créée : {destination} ({taille:.0f} Kio)")

    supprimees = purger(repertoire, retention, sauf=destination)
    if supprimees:
        print(f"{supprimees} sauvegarde(s) de plus de {retention} jours supprimée(s).")


if __name__ == "__main__":
    main()
