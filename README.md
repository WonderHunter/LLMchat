# LLMchat

Webapp de chat multi-utilisateurs. Chaque utilisateur apporte sa propre clé API (BYOK) pour
OpenRouter, OpenAI, Anthropic ou 1min.AI, et discute avec les modèles auxquels sa clé donne accès.

- **Backend** : Python 3.13, FastAPI, SQLite (SQLModel).
- **Frontend** : React, Vite, Tailwind.

Pour comprendre le projet en profondeur (architecture, choix techniques, trajet d'un
message), lire [docs/PROJET.md](docs/PROJET.md).

## Fonctionnalités

- Comptes par e-mail et mot de passe, session par cookie `HttpOnly`.
- Une clé par fournisseur, vérifiée auprès du fournisseur puis chiffrée en base. Elle n'est
  jamais renvoyée au navigateur.
- OpenRouter : modèles gratuits (`:free`) uniquement par défaut ; chaque utilisateur peut
  autoriser les modèles payants dans ses réglages. Le serveur applique ce réglage.
- Réponses en streaming, arrêt en cours de route (la réponse partielle est conservée),
  régénération, historique des conversations.
- Modification d'une question déjà envoyée : la suite de la conversation est remplacée.
- Pièces jointes : images (pour les modèles qui les lisent, signalés dans le sélecteur), PDF
  et fichiers texte.
- Tokens consommés et coût affichés sous chaque réponse, quand le fournisseur les communique.
- Panneau latéral pour le code long, avec aperçu des pages HTML et images SVG générées
  (dans une `iframe` isolée).
- Thème clair et sombre, affichage mobile.
- Compte : changement de mot de passe (qui déconnecte les autres appareils) et suppression
  du compte avec toutes ses données.
- Protection de la connexion : nombre de tentatives limité par adresse et par compte.

## Prérequis

- [uv](https://docs.astral.sh/uv/) (installe Python 3.13 si besoin)
- Node.js 22 et [pnpm](https://pnpm.io/)

## Installation

```bash
cd backend
uv sync
uv run python scripts/init_env.py
```

`init_env.py` crée le fichier `.env` à la racine avec des secrets générés. Les variables sont
décrites dans [.env.example](.env.example).

```bash
cd frontend
pnpm install
```

## Lancer en développement

Deux terminaux :

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8642
```

```bash
cd frontend
pnpm dev
```

L'app est sur <http://localhost:5180>. Vite relaie `/api` vers le backend (port `8642`,
modifiable avec la variable `API_PORT`).

### Mode démonstration

Pour essayer l'interface sans clé ni quota, avec des fournisseurs simulés :

```bash
cd backend
uv run python scripts/demo_server.py
```

Le compte de démonstration est affiché au démarrage (et défini en tête du script).

## Déployer avec Docker

Il faut un serveur joignable sur les ports 80 et 443, et un nom de domaine qui pointe dessus.

1. Créer `.env` à la racine (voir [.env.example](.env.example)) avec `SECRET_KEY`,
   `FERNET_KEY` et `DOMAIN` (par exemple `chat.exemple.fr`).
2. Lancer :

```bash
docker compose up -d --build
```

[Caddy](https://caddyserver.com/) obtient et renouvelle le certificat HTTPS tout seul, et
relaie les requêtes vers l'application, qui n'est pas exposée directement.

À savoir :

- La base SQLite est dans le volume `llmchat-data`. C'est lui qu'il faut sauvegarder, avec
  `FERNET_KEY` : sans cette clé, les clés API enregistrées sont illisibles.
- Les migrations de base s'appliquent toutes seules au démarrage.
- L'application tourne en un seul processus : la limitation des tentatives de connexion est
  tenue en mémoire, et SQLite n'accepte qu'un écrivain. Ne pas lancer plusieurs instances.

### Sans Docker

```bash
cd frontend
pnpm build
```

```bash
cd backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8642 --proxy-headers
```

Le backend sert alors l'interface compilée (`frontend/dist`) et l'API sur le même port. Le
placer derrière un reverse proxy HTTPS et mettre `COOKIE_SECURE=true` dans `.env`.
`--proxy-headers` fait confiance à l'adresse du visiteur transmise par le proxy local, dont
dépend la limitation des tentatives de connexion.

## Variables d'environnement

| Variable | Rôle |
| --- | --- |
| `SECRET_KEY` | Signe les cookies de session (32 caractères minimum). |
| `FERNET_KEY` | Chiffre les clés API des utilisateurs. La perdre rend ces clés illisibles. |
| `ALLOW_REGISTRATION` | `false` pour fermer les inscriptions. |
| `COOKIE_SECURE` | `true` quand l'app est servie en HTTPS. |
| `OPENROUTER_SERVICE_KEY` | Optionnelle. Envoyée uniquement pour lire le catalogue OpenRouter, jamais pour le chat. Le catalogue étant public, elle peut rester vide. |
| `CATALOG_REFRESH_MINUTES` | Fréquence de rafraîchissement du catalogue OpenRouter (30 par défaut). |
| `DATABASE_URL` | Par défaut `backend/llmchat.db`. |
| `DOMAIN` | Nom de domaine servi par Caddy. Utilisé uniquement par `compose.yaml`. |

## Faire évoluer la base

Après avoir modifié un modèle dans `backend/app/models.py`, générer la migration puis la relire :

```bash
cd backend
uv run alembic revision --autogenerate -m "description du changement"
```

Un test vérifie que les migrations et les modèles décrivent le même schéma.

## Tests

```bash
cd backend
uv run pytest
```

```bash
cd frontend
pnpm build
pnpm lint
```

Les tests du backend n'appellent aucun service externe : les fournisseurs sont simulés.

## Organisation du code

```
backend/app/
  providers/     un connecteur par fournisseur (OpenRouter, OpenAI, Anthropic, 1min.AI)
  services/      catalogue de modèles (rafraîchi en tâche de fond pour OpenRouter)
  routers/       auth, clés, modèles, conversations, chat (SSE)
frontend/src/
  api/           client HTTP, lecture du flux SSE, requêtes
  chat/          état du chat, envoi et régénération, règles du panneau latéral
  components/    barre latérale, messages, saisie, sélecteur de modèle, réglages, panneau
  pages/         connexion, inscription, chat
```

## Branches

Le dépôt suit gitflow : `main` pour les versions publiées, `develop` pour l'intégration,
une branche `feature/<nom>` par évolution.
