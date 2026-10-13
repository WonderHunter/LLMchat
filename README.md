# LLMchat

Webapp de chat multi-utilisateurs. Chaque utilisateur apporte sa propre clé API (BYOK) pour
OpenRouter, OpenAI ou Anthropic, et discute avec les modèles auxquels sa clé donne accès.

- **Backend** : Python 3.13, FastAPI, SQLite (SQLModel).
- **Frontend** : React, Vite, Tailwind.

## Fonctionnalités

- Comptes par e-mail et mot de passe, session par cookie `HttpOnly`.
- Une clé par fournisseur, vérifiée auprès du fournisseur puis chiffrée en base. Elle n'est
  jamais renvoyée au navigateur.
- OpenRouter : modèles gratuits (`:free`) uniquement par défaut ; chaque utilisateur peut
  autoriser les modèles payants dans ses réglages. Le serveur applique ce réglage.
- Réponses en streaming, arrêt en cours de route (la réponse partielle est conservée),
  régénération, historique des conversations.
- Panneau latéral pour le code long, avec aperçu des pages HTML et images SVG générées
  (dans une `iframe` isolée).
- Thème clair et sombre, affichage mobile.

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

## Lancer en production

```bash
cd frontend
pnpm build
```

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8642
```

Le backend sert alors l'interface compilée (`frontend/dist`) et l'API sur le même port.
Derrière HTTPS, mettre `COOKIE_SECURE=true` dans `.env`.

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
  providers/     un connecteur par fournisseur (OpenRouter, OpenAI, Anthropic)
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
