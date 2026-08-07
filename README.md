# Dashboard FI

Tableau de bord d'investissement auto-hébergé : vous créez vos propres comptes (PEA,
compte-titres, PER, assurance vie, métaux précieux, cryptomonnaies), y saisissez vos
positions, et le dashboard suit les cours en direct, l'historique de valorisation, les
dividendes, la fiscalité et le rééquilibrage.

Le projet ne contient **aucune donnée de portefeuille** : la base est vide au premier
lancement et tout reste sur votre machine.

![Vue d'ensemble](docs/apercu.png)

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Types de comptes](#types-de-comptes)
- [Installation](#installation)
- [Premiers pas](#premiers-pas)
- [Cours automatiques](#cours-automatiques)
- [Options](#options) — clé IA, authentification, Telegram
- [HTTPS](#https)
- [Déploiement permanent](#déploiement-permanent-debian)
- [API](#api)
- [Structure du projet](#structure-du-projet)

## Fonctionnalités

| Onglet | Contenu |
|---|---|
| **Vue d'ensemble** | Patrimoine total, répartition par compte et par type d'enveloppe, performance, top 10 des positions, répartition sectorielle et géographique |
| **Mes comptes** | Création, modification et suppression des comptes ; une page par compte avec le détail des positions |
| **Simulation** | Projection patrimoniale (horizon, rendement, versements mensuels, inflation, scénarios haussier/baissier) |
| **Dividendes** | Saisie des versements, revenus par mois et par année, top positions, TRI (XIRR) par ligne |
| **Historique** | Évolution du patrimoine total et par compte, comparaison à des indices (CAC 40, MSCI World, S&P 500, Nasdaq 100, MSCI Europe) |
| **Fiscalité** | Règles et simulateur de sortie adaptés au type de chaque compte et à sa date d'ouverture |
| **Rebalancing** | Allocation cible par compte, écarts, et mouvements d'achat/allègement recommandés |
| **Arbitrage IA** | Analyse du portefeuille par l'API Anthropic (optionnel, clé requise) |

Également : thème clair/sombre, masquage des montants, export CSV, application installable
(PWA) utilisable hors ligne, et interface responsive jusqu'au format mobile.

## Types de comptes

Chaque compte que vous créez porte un type. Celui-ci détermine l'unité des quantités, la
devise proposée par défaut et surtout les règles appliquées dans l'onglet Fiscalité.

| Type | Unité | Seuil de détention | Simulateur de sortie |
|---|---|---|---|
| **PEA** | titres | 5 ans | Exonération d'IR après 5 ans, prélèvements sociaux à 17,2 % ; flat tax et clôture avant |
| **CTO** | titres | — | Flat tax de 30 % (12,8 % IR + 17,2 % PS) |
| **PER** | parts | — | Barème de l'IR sur les versements déduits, 30 % sur la quote-part de gains |
| **Assurance vie** | parts | 8 ans | Abattement de 4 600 € / 9 200 €, IR réduit à 7,5 %, comparé au régime d'avant 8 ans |
| **Métaux précieux** | onces | 22 ans | Taxe forfaitaire de 11,5 % comparée au régime des plus-values (36,2 % avec abattement) |
| **Cryptomonnaies** | unités | — | Flat tax de 30 %, exonération sous 305 € de cessions annuelles |

Les taux sont regroupés dans [`catalog.py`](catalog.py) — un seul fichier à mettre à jour
si la législation change. Ces simulations sont indicatives et ne remplacent pas l'avis
d'un conseiller fiscal.

## Installation

Prérequis : Python 3.9 ou plus récent.

```bash
git clone https://github.com/zebulon94fr/Dashboard-FI-pub.git
cd Dashboard-FI-pub

python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

Le dashboard est accessible sur [http://localhost:8742](http://localhost:8742). La base
SQLite (`dashboard.db`) est créée automatiquement au premier lancement.

Variables d'environnement :

| Variable | Défaut | Description |
|---|---|---|
| `DASHBOARD_PORT` | `8742` | Port d'écoute |
| `DASHBOARD_HOST` | `0.0.0.0` | Interface d'écoute |
| `DASHBOARD_DB` | `./dashboard.db` | Emplacement de la base SQLite |
| `DASHBOARD_SSL_CERT` | — | Certificat TLS (voir [HTTPS](#https)) |
| `DASHBOARD_SSL_KEY` | — | Clé privée TLS |

## Premiers pas

1. **Créez un compte** via le bouton `+ Compte` : choisissez le type d'enveloppe, donnez-lui
   un nom, et renseignez la date d'ouverture (elle sert aux règles fiscales liées à la durée
   de détention).
2. **Ajoutez vos positions** avec `+ Position`. Renseignez le ticker Yahoo Finance pour que
   le cours se mette à jour tout seul ; sans ticker, le cours reste celui que vous saisissez.
3. **Actualisez les cours** — l'historique se construit à partir de là, un point par
   actualisation et un point de clôture par jour.

Pour voir l'interface remplie avant d'y saisir vos vraies données :

```bash
python scripts/demo_data.py           # portefeuille fictif de 6 comptes
python scripts/demo_data.py --reset   # repartir d'une base vide
```

## Cours automatiques

Les cours viennent de Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance).
Le ticker se trouve sur [finance.yahoo.com](https://finance.yahoo.com) — par exemple
`BN.PA` (Danone), `MSFT` (Microsoft), `BTC-EUR` (Bitcoin), `GC=F` (once d'or).

Le moteur est identique pour toutes les enveloppes : le cours est récupéré dans la devise
de la position, puis converti en euros au taux du moment. Les valorisations, plus-values et
totaux sont donc toujours en euros, tandis que cours et PRU restent affichés dans leur
devise d'origine.

Les listes de tickers crypto et métaux sont proposées en autocomplétion, mais n'importe
quel ticker Yahoo reste utilisable.

## Options

### Analyse IA

L'onglet *Arbitrage IA* utilise l'API Anthropic. Renseignez votre clé directement dans
l'interface, ou dans `settings.json` :

```bash
cp settings.json.example settings.json
```

```json
{ "anthropicKey": "sk-ant-..." }
```

`settings.json` est ignoré par git : la clé ne quitte pas votre machine. Sans clé, tout le
reste du dashboard fonctionne normalement.

### Authentification

Par défaut, il n'y a pas de mot de passe — pratique en local. Si le serveur est joignable
depuis d'autres appareils, activez une authentification HTTP Basic :

```bash
python scripts/set_password.py             # activer / modifier
python scripts/set_password.py --disable   # désactiver
```

Seul le hash du mot de passe est stocké dans `settings.json`. Les appels venant de
`127.0.0.1` (par exemple le timer de rafraîchissement) ne sont jamais bloqués.

### Résumé Telegram

Envoie un résumé du portefeuille (répartition, performance, meilleures et pires positions,
et une analyse IA si une clé est configurée) sur Telegram, à la demande via le bouton
**📱 Telegram** ou automatiquement via un timer systemd.

```bash
python scripts/set_telegram.py
```

Le script explique comment créer un bot via `@BotFather` et récupérer votre `chat_id`.

## HTTPS

```bash
./scripts/generate_cert.sh                 # localhost uniquement
./scripts/generate_cert.sh 192.168.1.50    # + accessible depuis le réseau local
DASHBOARD_SSL_CERT=certs/cert.pem DASHBOARD_SSL_KEY=certs/key.pem python app.py
```

Le certificat étant auto-signé, le navigateur affiche un avertissement la première fois.

## Déploiement permanent (Debian)

```bash
# 1. Installer
sudo mkdir -p /opt/dashboard-fi && sudo chown $USER /opt/dashboard-fi
git clone https://github.com/zebulon94fr/Dashboard-FI-pub.git /opt/dashboard-fi
cd /opt/dashboard-fi
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. Certificat TLS (adapter à l'IP ou au nom d'hôte du serveur)
./scripts/generate_cert.sh 192.168.1.50

# 3. Utilisateur dédié
sudo useradd -r -s /usr/sbin/nologin dashboard
sudo chown -R dashboard:dashboard /opt/dashboard-fi

# 4. Service systemd
sudo cp deploy/dashboard-fi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard-fi
```

Le service redémarre automatiquement après un crash et au reboot, via `gunicorn`. Adaptez
les chemins dans les fichiers de `deploy/` si votre répertoire d'installation diffère.

Timers optionnels, à installer de la même façon :

| Timer | Rôle | Fréquence par défaut |
|---|---|---|
| `dashboard-fi-refresh.timer` | Actualise les cours sans ouvrir le dashboard | toutes les heures |
| `dashboard-fi-backup.timer` | Sauvegarde `dashboard.db` dans `backups/` | quotidienne, rétention 14 jours |
| `dashboard-fi-telegram.timer` | Envoie le résumé Telegram | samedi 9 h |

```bash
sudo cp deploy/dashboard-fi-refresh.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard-fi-refresh.timer
systemctl list-timers | grep dashboard-fi
```

## API

Toutes les routes sont sous `/api`. Le frontend n'utilise rien d'autre — un script ou un
autre client peut donc piloter le dashboard de la même façon.

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/account-types` | Catalogue des types d'enveloppes et de leurs règles |
| `GET` | `/api/data` | Portefeuille complet : comptes, positions, historique |
| `GET` `POST` | `/api/accounts` | Liste et création de comptes |
| `PUT` `DELETE` | `/api/accounts/<id>` | Modification et suppression (positions et dividendes en cascade) |
| `POST` | `/api/accounts/cibles` | Allocations cibles du rebalancing |
| `GET` `POST` | `/api/accounts/<id>/positions` | Positions d'un compte |
| `PUT` `DELETE` | `/api/positions/<id>` | Modification, déplacement vers un autre compte, suppression |
| `GET` | `/api/quotes` | Actualise cours et taux de change |
| `GET` | `/api/stats` | Agrégats, meilleures et pires positions, variation 24 h |
| `GET` `POST` | `/api/dividendes` | Versements enregistrés |
| `PUT` `DELETE` | `/api/dividendes/<id>` | Modification et suppression |
| `GET` | `/api/tri?nom=&account_id=` | TRI d'une position |
| `GET` | `/api/benchmark?days=` | Indices normalisés sur le capital de départ |
| `GET` | `/api/export/csv` | Export du portefeuille |
| `POST` | `/api/telegram/send` | Envoi du résumé |

Les erreurs de validation renvoient `400` avec un message en français dans `{"error": …}`.

## Structure du projet

```
Dashboard-FI-pub/
├── app.py                  # Point d'entrée Flask (+ auth HTTP Basic optionnelle)
├── config.py               # Chemins et configuration
├── catalog.py              # Types d'enveloppes, règles fiscales, tickers de référence
├── backend/                # Logique métier
│   ├── accounts.py            # CRUD des comptes
│   ├── positions.py           # CRUD des positions, calculs, historique
│   ├── quotes.py              # Cours et taux de change (yfinance)
│   ├── stats.py               # Agrégats
│   ├── dividendes.py          # Dividendes et TRI
│   ├── benchmark.py           # Indices de comparaison
│   ├── export.py              # Export CSV
│   ├── telegram.py            # Résumé Telegram
│   ├── claude.py              # Appel à l'API Anthropic
│   ├── settings.py            # settings.json
│   └── db.py                  # Connexion SQLite et schéma
├── routes/                 # Un blueprint Flask par domaine d'API
├── static/                 # Frontend (HTML + CSS + modules ES natifs)
│   ├── js/                    # Un module par onglet, api.js centralise le réseau
│   ├── vendor/                # Chart.js servi localement (MIT)
│   ├── manifest.json          # PWA
│   └── sw.js                  # Service worker : cache le shell, jamais /api
├── scripts/                # demo_data, set_password, set_telegram, generate_cert, backup…
├── deploy/                 # Unités systemd
├── dashboard.db            # Base SQLite (non versionnée, créée au lancement)
└── settings.json           # Clé API, identifiants, Telegram (non versionné)
```

### Modèle de données

Aucune enveloppe n'est câblée dans le schéma : un compte est une ligne de `accounts`, et
positions, historique et dividendes s'y rattachent par `account_id`. Ajouter un type
d'enveloppe se fait donc dans `catalog.py`, sans migration.

```
accounts ──┬── positions ──── price_history
           ├── dividendes
           └── history_daily / history_intraday   (account_id = 0 : total du portefeuille)
```

## Vie privée

Tout est local : la base SQLite, les identifiants et la clé API restent sur votre machine et
sont exclus du dépôt par `.gitignore`. Le dashboard ne contacte l'extérieur que pour
récupérer les cours (Yahoo Finance), et — si vous les configurez — l'API Anthropic et
Telegram. Chart.js est servi depuis `static/vendor/` plutôt qu'un CDN : aucune requête
tierce au chargement de la page.
