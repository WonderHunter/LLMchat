# LLMchat : le projet de bout en bout

Ce document explique ce que fait l'application, avec quoi elle est construite, pourquoi ces
choix ont été faits, et comment les morceaux s'emboîtent. Il est écrit pour être lu de haut en
bas par quelqu'un qui veut comprendre le projet, pas seulement l'installer (pour ça, voir le
[README](../README.md)).

État décrit : branche `develop`, 13 octobre 2026.

## Sommaire

1. [Ce que fait l'application](#1-ce-que-fait-lapplication)
2. [Vue d'ensemble](#2-vue-densemble)
3. [Les technologies et pourquoi elles ont été choisies](#3-les-technologies-et-pourquoi-elles-ont-été-choisies)
4. [Organisation du dépôt](#4-organisation-du-dépôt)
5. [Les données](#5-les-données)
6. [Le backend en détail](#6-le-backend-en-détail)
7. [Le frontend en détail](#7-le-frontend-en-détail)
8. [Le trajet d'un message, étape par étape](#8-le-trajet-dun-message-étape-par-étape)
9. [Sécurité](#9-sécurité)
10. [Tests](#10-tests)
11. [Outillage : développement, démo, CI, Docker, git](#11-outillage--développement-démo-ci-docker-git)
12. [Décisions et compromis](#12-décisions-et-compromis)
13. [Limites connues et suites possibles](#13-limites-connues-et-suites-possibles)
14. [Glossaire](#14-glossaire)

---

## 1. Ce que fait l'application

LLMchat est une application web de discussion avec des modèles de langage, dans l'esprit de
ChatGPT et de Claude. Sa particularité est le **BYOK** (*bring your own key*) : l'application
ne paie aucun modèle. Chaque utilisateur crée un compte, enregistre sa propre clé API chez un
ou plusieurs fournisseurs, et discute avec les modèles auxquels sa clé donne accès.

Quatre fournisseurs sont pris en charge :

| Fournisseur | Ce qu'il apporte | Particularité dans l'app |
| --- | --- | --- |
| **OpenRouter** | Un guichet unique vers des centaines de modèles, dont des gratuits (suffixe `:free`) | Limité aux modèles gratuits par défaut ; l'utilisateur peut autoriser les payants |
| **OpenAI** | Les modèles GPT | Liste des modèles lue avec la clé de l'utilisateur |
| **Anthropic** | Les modèles Claude | Liste des modèles lue avec la clé de l'utilisateur |
| **1min.AI** | Une seule clé pour des modèles de plusieurs éditeurs (OpenAI, DeepSeek, Qwen, Mistral…), payés en crédits | Texte seul : aucun de ses modèles ne lit les images |

Ce qu'un utilisateur peut faire :

- créer un compte, se connecter, changer de mot de passe, supprimer son compte ;
- enregistrer, remplacer ou supprimer une clé par fournisseur ;
- choisir un modèle, avec l'indication « gratuit » ou « payant » et une icône quand le modèle
  lit les images ;
- discuter : la réponse s'affiche au fil de l'eau, on peut l'arrêter, la régénérer, ou modifier
  une question déjà envoyée ;
- joindre des images, des PDF et des fichiers texte ;
- voir, sous chaque réponse, le nombre de tokens consommés et le coût quand il est connu ;
- ouvrir le code long dans un panneau latéral, avec un aperçu des pages HTML et images SVG ;
- retrouver ses conversations, les renommer, les supprimer ;
- basculer entre thème clair et sombre, sur ordinateur comme sur téléphone.

L'interface reprend la **structure de ChatGPT** (barre latérale d'historique, sélecteur de
modèle en haut, actions sous les messages) et l'**habillage de Claude** (fond crème, accent
terracotta, titres en serif, zone de saisie arrondie).

---

## 2. Vue d'ensemble

L'application est en deux parties qui se parlent par HTTP : une interface qui tourne dans le
navigateur, et un serveur Python qui détient les données et parle aux fournisseurs.

```
┌────────────────────┐        ┌──────────────────────────────┐        ┌────────────────┐
│  Navigateur        │        │  Serveur (FastAPI, Python)   │        │  Fournisseurs  │
│                    │  HTTP  │                              │ HTTPS  │                │
│  React             │ ─────► │  /api/auth      comptes      │ ─────► │  OpenRouter    │
│  (interface)       │ cookie │  /api/keys      clés         │  clé   │  OpenAI        │
│                    │        │  /api/models    catalogue    │  de    │  Anthropic     │
│                    │        │                              │ l'uti- │  1min.AI       │
│                    │ ◄───── │  /api/chat      discussion   │ lisa-  │                │
│                    │  flux  │  /api/attachments fichiers   │ teur   │                │
└────────────────────┘  SSE   │                              │        └────────────────┘
                              │        SQLite (un fichier)   │
                              └──────────────────────────────┘
```

Trois idées structurent tout le reste :

1. **Le navigateur ne voit jamais une clé API.** Il l'envoie une fois au serveur, qui la
   vérifie, la chiffre et la range. Ensuite, c'est le serveur qui appelle les fournisseurs.
2. **Le serveur ne fait confiance à rien de ce qui vient du navigateur.** Chaque requête est
   rattachée à un utilisateur par son cookie de session, et chaque donnée est filtrée par cet
   utilisateur. Les règles (modèle autorisé, fichier accepté) sont appliquées côté serveur,
   même si l'interface les applique déjà.
3. **Les fournisseurs sont interchangeables.** Le cœur de l'application parle à une interface
   commune ; chaque fournisseur a son connecteur qui traduit vers son API.

Selon le contexte, ce qui se trouve entre le navigateur et le serveur change :

| Contexte | Qui sert l'interface | Qui reçoit `/api` |
| --- | --- | --- |
| Développement | Vite, port 5180, avec rechargement à chaud | Vite relaie vers FastAPI, port 8642 |
| Production | FastAPI lui-même (l'interface compilée) | FastAPI, derrière Caddy qui gère le HTTPS |

Dans les deux cas le navigateur ne parle qu'à **une seule origine**. C'est ce qui permet
d'utiliser un simple cookie de session sans configuration CORS.

---

## 3. Les technologies et pourquoi elles ont été choisies

### Backend

| Brique | Version | Rôle | Pourquoi ce choix |
| --- | --- | --- | --- |
| **Python** | 3.13 | Langage du serveur | Demandé au départ ; c'est aussi le langage où les SDK des fournisseurs sont les mieux tenus |
| **uv** | 0.9 | Installe Python et les dépendances, lance les commandes | Rapide, un seul outil, verrouille les versions dans `uv.lock` |
| **FastAPI** | 0.143 | Framework web : routes, validation, documentation de l'API | Asynchrone, donc à l'aise avec le streaming ; valide les entrées à partir des types |
| **Starlette** | 1.7 | Socle de FastAPI (requêtes, réponses en flux, middleware) | Vient avec FastAPI |
| **Uvicorn** | 0.54 | Serveur qui exécute l'application | Le serveur ASGI de référence pour FastAPI |
| **Pydantic** | 2.14 | Décrit et valide les données échangées | Vient avec FastAPI ; `pydantic-settings` lit la configuration depuis `.env` |
| **SQLModel** | 0.0.48 | Décrit les tables comme des classes Python | Écrit par l'auteur de FastAPI ; un seul modèle sert à la base et à la validation |
| **SQLAlchemy** | 2.1 | Moteur sous SQLModel | Vient avec SQLModel |
| **SQLite** | intégré à Python | Base de données, dans un fichier | Aucune installation, sauvegarde par copie d'un fichier, suffisant pour ce volume |
| **Alembic** | 1.20 | Migrations : fait évoluer la base sans perdre les données | L'outil standard avec SQLAlchemy |
| **pwdlib + argon2** | 0.3 / 25.1 | Hache les mots de passe | Argon2 est l'algorithme recommandé aujourd'hui ; `passlib`, l'ancien choix, n'est plus maintenu |
| **PyJWT** | 2.15 | Signe le jeton de session | Simple, sans dépendances |
| **cryptography** | 50.0 | Chiffre les clés API (Fernet) | La bibliothèque de référence en Python |
| **openai** (SDK) | 3.29 | Parle à OpenAI et à OpenRouter | OpenRouter parle le même protocole : un seul connecteur pour deux fournisseurs |
| **anthropic** (SDK) | 1.13 | Parle à Anthropic | SDK officiel ; gère le format propre à Claude |
| **httpx** | 0.28 | Appels HTTP directs à OpenRouter (catalogue, vérification de clé) | Ces deux endpoints n'existent dans aucun SDK |
| **pypdf** | 6.20 | Extrait le texte des PDF | Pur Python, rien à installer sur le système |
| **python-multipart** | 0.0.32 | Lit les fichiers envoyés par formulaire | Requis par FastAPI pour les envois de fichiers |

Outils de développement : **pytest** 9.1 (tests), **pytest-asyncio** (tests de code
asynchrone), **respx** (simule les réponses HTTP d'OpenRouter), **ruff** 0.17 (lint et mise en
forme).

### Frontend

| Brique | Version | Rôle | Pourquoi ce choix |
| --- | --- | --- | --- |
| **React** | 19 | Construit l'interface en composants | Choix validé au départ ; le plus adapté à une interface de chat riche |
| **TypeScript** | 6.0 | JavaScript avec des types | Attrape les erreurs avant l'exécution ; les types décrivent ce que renvoie l'API |
| **Vite** | 8.3 | Serveur de développement et compilation | Démarrage instantané, rechargement à chaud, relais vers l'API intégré |
| **Tailwind CSS** | 4.3 | Styles, par classes utilitaires | Permet de régler finement l'apparence sans feuille de style séparée |
| **@tailwindcss/typography** | 0.5 | Met en forme le texte des réponses (titres, listes, tableaux) | Évite de styler chaque balise Markdown à la main |
| **React Router** | 7.18 | Navigation : `/login`, `/`, `/c/<id>` | Chaque conversation a son adresse, donc rechargeable et partageable entre onglets |
| **TanStack Query** | 5.104 | Charge et met en cache les données du serveur | Gère chargement, cache et rafraîchissement, qu'on écrirait sinon à la main |
| **Zustand** | 5.0 | État local de l'interface | Minuscule ; accessible aussi hors des composants, ce dont le streaming a besoin |
| **react-markdown** | 10.1 | Affiche le Markdown des réponses | N'interprète pas le HTML brut : une réponse ne peut pas injecter de script |
| **remark-gfm** | 4.0 | Tableaux, listes de tâches, liens automatiques | Les modèles en produisent souvent |
| **rehype-highlight** + **highlight.js** | 7.0 / 11.12 | Coloration syntaxique du code | Léger, reconnaît les langages courants |
| **lucide-react** | 1.55 | Icônes | Jeu cohérent, importé icône par icône |
| **pnpm** | 11.1 | Installe les dépendances JavaScript | Rapide, économe en disque |
| **oxlint** | 1.81 | Lint | Fourni par le modèle de projet Vite, très rapide |

### Infrastructure

| Brique | Rôle | Pourquoi ce choix |
| --- | --- | --- |
| **Docker** | Emballe l'application dans une image prête à déployer | Même environnement partout |
| **Caddy** 2 | Reverse proxy, HTTPS automatique | Obtient et renouvelle les certificats sans configuration |
| **GitHub Actions** | Lance tests, lint et build à chaque push | Intégré à GitHub, gratuit pour ce volume |
| **git-flow** | Organisation des branches | Demandé pour ce projet |

---

## 4. Organisation du dépôt

```
LLMchat/
├── README.md                 installation, lancement, déploiement
├── .env.example              modèle de configuration (le vrai .env n'est pas versionné)
├── Dockerfile                image : compile l'interface, puis installe le backend
├── compose.yaml              déploiement : l'application + Caddy
├── deploy/Caddyfile          configuration de Caddy
├── .github/workflows/ci.yml  intégration continue
├── docs/PROJET.md            ce document
│
├── backend/
│   ├── pyproject.toml        dépendances et réglages des outils
│   ├── uv.lock               versions exactes installées
│   ├── alembic.ini           pour créer une migration en ligne de commande
│   ├── app/
│   │   ├── main.py           assemble l'application : routes, en-têtes, tâche de fond
│   │   ├── config.py         configuration lue depuis .env
│   │   ├── db.py             connexion à la base, application des migrations
│   │   ├── models.py         les tables
│   │   ├── schemas.py        la forme des réponses de l'API
│   │   ├── security.py       mots de passe, jeton de session, chiffrement des clés
│   │   ├── deps.py           « qui est l'utilisateur de cette requête ? »
│   │   ├── ratelimit.py      limitation des tentatives
│   │   ├── attachments.py    règles et lecture des fichiers joints
│   │   ├── providers/        un connecteur par fournisseur
│   │   │   ├── base.py           interface commune et erreurs
│   │   │   ├── openai_compat.py  OpenRouter, OpenAI et 1min.AI
│   │   │   ├── anthropic.py      Anthropic
│   │   │   └── registry.py       la liste des fournisseurs disponibles
│   │   ├── services/catalog.py   catalogue des modèles
│   │   ├── routers/          les routes de l'API, par sujet
│   │   │   ├── auth.py  keys.py  models.py  conversations.py  attachments.py  chat.py
│   │   └── migrations/       historique des évolutions de la base
│   ├── scripts/
│   │   ├── init_env.py       crée .env avec des secrets générés
│   │   └── demo_server.py    serveur de démonstration, fournisseurs simulés
│   └── tests/                138 tests
│
└── frontend/
    ├── package.json          dépendances
    ├── vite.config.ts        port, relais vers l'API
    ├── index.html            page d'entrée
    ├── public/               logo et icônes, servis tels quels
    ├── branding/             logo d'origine et script qui génère ses déclinaisons
    └── src/
        ├── main.tsx          point d'entrée
        ├── App.tsx           routes, protection des pages, thème
        ├── index.css         couleurs des thèmes, styles du texte et du code
        ├── api/              dialogue avec le serveur
        │   ├── client.ts         requêtes, envoi de fichier, lecture du flux
        │   ├── hooks.ts          chargements et actions (TanStack Query)
        │   └── types.ts          forme des données de l'API
        ├── chat/             logique du chat, sans affichage
        │   ├── store.ts          état local (Zustand)
        │   ├── actions.ts        envoyer, régénérer, modifier, arrêter
        │   ├── useSelection.ts   modèle choisi
        │   └── artifacts.ts      règles du panneau latéral
        ├── components/       les morceaux d'interface
        └── pages/            AuthPage (connexion, inscription), ChatPage
```

Ordre de grandeur : environ 1 900 lignes pour le backend, 1 850 pour ses tests, 2 500 pour le
frontend.

**Par où commencer pour lire le code.** Côté serveur : `models.py` (les données), puis
`providers/base.py` (le contrat des fournisseurs), puis `routers/chat.py` (le cœur). Côté
interface : `chat/actions.ts` (ce qui se passe quand on envoie un message), puis
`pages/ChatPage.tsx` (comment l'écran s'assemble).

---

## 5. Les données

Cinq tables, dans un seul fichier SQLite.

```
user ──┬──< providerkey          une clé chiffrée par fournisseur
       ├──< conversation ──< message ──< attachment
       └──< attachment            (aussi rattachée à son propriétaire)
```

| Table | Colonnes principales | Rôle |
| --- | --- | --- |
| `user` | `email` (unique), `password_hash`, `token_version` | Un compte |
| `providerkey` | `user_id`, `provider`, `key_enc`, `last4`, `free_only` | Une clé API chiffrée. Unique par couple utilisateur / fournisseur |
| `conversation` | `id` (aléatoire), `user_id`, `title`, `provider`, `model`, dates | Une discussion et le dernier modèle utilisé |
| `message` | `conversation_id`, `role`, `content`, `provider`, `model`, `input_tokens`, `output_tokens`, `cost` | Une question (`user`) ou une réponse (`assistant`) |
| `attachment` | `user_id`, `message_id`, `kind`, `filename`, `media_type`, `size`, `data`, `text` | Un fichier joint |

Points à retenir :

- **`key_enc`** contient la clé chiffrée ; **`last4`** ses quatre derniers caractères, seule
  trace affichée à l'utilisateur.
- **`free_only`** ne sert que pour OpenRouter : vrai par défaut, il limite aux modèles `:free`.
- **`token_version`** augmente à chaque changement de mot de passe. Un jeton de session émis
  avant ne correspond plus : c'est ce qui déconnecte les autres appareils.
- L'identifiant d'une **conversation** est une chaîne aléatoire de 32 caractères, pas un
  numéro : il apparaît dans l'adresse (`/c/<id>`) et ne doit pas se deviner.
- Une **pièce jointe** a `message_id` vide entre le moment où le fichier est envoyé et celui
  où le message part. Pour une image, `data` contient ses octets ; pour un document, `text`
  contient son texte et l'original n'est pas gardé.
- Les **suppressions se propagent** : supprimer une conversation supprime ses messages, donc
  leurs pièces jointes ; supprimer un compte supprime tout ce qui lui appartient.

### Migrations

La base n'est jamais créée ni modifiée « à la main ». Chaque évolution est un fichier dans
`backend/app/migrations/versions/` :

| Migration | Contenu |
| --- | --- |
| `0001` | Schéma initial : utilisateurs, clés, conversations, messages |
| `0002` | `token_version` sur les utilisateurs |
| `0003` | Tokens et coût sur les messages |
| `0004` | Table des pièces jointes |

Au démarrage, le serveur applique celles qui manquent (`init_db()` dans `db.py`). Une base
créée avant l'arrivée des migrations est reconnue et reprise telle quelle. Un test vérifie que
le schéma obtenu par les migrations est exactement celui que décrivent les modèles : on ne peut
donc pas modifier un modèle en oubliant sa migration sans que la CI le signale.

---

## 6. Le backend en détail

### 6.1 Configuration (`config.py`)

Lue depuis le fichier `.env` à la racine, ou depuis les variables d'environnement.

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SECRET_KEY` | obligatoire, 32 caractères minimum | Signe les jetons de session |
| `FERNET_KEY` | obligatoire | Chiffre les clés API |
| `DATABASE_URL` | `backend/llmchat.db` | Emplacement de la base |
| `ALLOW_REGISTRATION` | `true` | Ferme les inscriptions si `false` |
| `COOKIE_SECURE` | `false` | À `true` en HTTPS : cookie envoyé seulement sur connexion chiffrée |
| `OPENROUTER_SERVICE_KEY` | vide | Optionnelle, pour lire le catalogue OpenRouter |
| `CATALOG_REFRESH_MINUTES` | `30` | Fréquence de rafraîchissement du catalogue ; `0` le désactive |
| `DEMO_MODE` | `false` | Activé par le serveur de démonstration |

### 6.2 Comptes et sessions (`security.py`, `deps.py`, `routers/auth.py`)

**Mot de passe.** Il n'est jamais stocké. On garde son empreinte Argon2, calculée par `pwdlib`.
À la connexion, on recalcule et on compare. Quand l'e-mail est inconnu, le serveur compare
quand même avec une empreinte factice : la réponse prend le même temps, ce qui empêche de
deviner quels e-mails ont un compte.

**Session.** Après connexion, le serveur pose un cookie `llmchat_session` contenant un jeton
JWT signé avec `SECRET_KEY`. Le jeton porte l'identifiant de l'utilisateur, sa version de
session et une date d'expiration (30 jours). Le cookie est :

- `HttpOnly` : le JavaScript de la page ne peut pas le lire, donc un script injecté ne peut pas
  le voler ;
- `SameSite=Lax` : il n'est pas envoyé par une requête lancée depuis un autre site, ce qui
  protège des attaques CSRF ;
- `Secure` en production : jamais transmis en clair.

À chaque requête, `get_current_user` (`deps.py`) lit le cookie, vérifie la signature, charge
l'utilisateur et compare la version de session. Toutes les routes protégées en dépendent.

**Changement de mot de passe et suppression.** Les deux redemandent le mot de passe actuel. Le
changement augmente `token_version` et renvoie un nouveau cookie : l'appareil qui a fait le
changement reste connecté, les autres sont déconnectés.

### 6.3 Limitation des tentatives (`ratelimit.py`)

Un compteur en mémoire, par fenêtre glissante :

| Ce qui est compté | Limite |
| --- | --- |
| Échecs de connexion depuis une même adresse IP | 20 par quart d'heure |
| Échecs de connexion sur un même compte | 8 par quart d'heure |
| Créations de compte depuis une même adresse IP | 5 par heure |

Au-delà, le serveur répond 429 avec le délai à attendre. Une connexion réussie remet à zéro le
compteur du compte. Le compteur par compte protège d'une attaque ciblée, celui par adresse
d'une attaque qui essaie beaucoup de comptes.

Deux conséquences à connaître. Le compteur vit en mémoire : il repart de zéro au redémarrage et
suppose **un seul processus**. Et derrière un reverse proxy, le serveur doit être lancé avec
`--proxy-headers` pour voir la vraie adresse du visiteur, sinon tout le monde partagerait le
même compteur.

### 6.4 Les fournisseurs (`providers/`)

Tout fournisseur implémente le même contrat (`base.py`) :

| Méthode | Rôle |
| --- | --- |
| `validate_key(key)` | Vérifie la clé par un appel léger ; lève `InvalidKey` si elle est refusée |
| `list_models(key)` | Renvoie les modèles de chat utilisables, sous forme de `ModelInfo` |
| `stream_chat(key, model, messages)` | Produit la réponse morceau par morceau, puis la consommation |

`ModelInfo` décrit un modèle de façon uniforme : identifiant, nom, gratuit ou non, lit les
images ou non, taille de contexte, plafond de sortie, prix d'entrée et de sortie.

Les erreurs sont **normalisées** : quel que soit le fournisseur, le reste de l'application ne
voit que ces cas, chacun avec un message en français affichable tel quel.

| Erreur | Signification |
| --- | --- |
| `InvalidKey` | Clé invalide ou révoquée |
| `QuotaExceeded` | Trop de requêtes (fréquent sur les modèles gratuits) |
| `InsufficientCredit` | Plus de crédit sur le compte du fournisseur |
| `ModelUnavailable` | Modèle introuvable ou inaccessible avec cette clé |
| `ProviderUnavailable` | Fournisseur injoignable |
| `ProviderError` | Tout le reste |

Les quatre connecteurs :

| | OpenRouter | OpenAI | Anthropic | 1min.AI |
| --- | --- | --- | --- | --- |
| Fichier | `openai_compat.py` | `openai_compat.py` | `anthropic.py` | `openai_compat.py` |
| Bibliothèque | SDK `openai` (adresse changée) + `httpx` | SDK `openai` | SDK `anthropic` | SDK `openai` (adresse changée) |
| Vérification de clé | `GET /api/v1/key` | Liste des modèles | Liste des modèles | Liste des modèles |
| Liste des modèles | Catalogue public, sans clé | Avec la clé, filtrée sur le nom | Avec la clé | Avec la clé |
| Sait si un modèle lit les images | Oui (catalogue) | Non : déduit du nom | Oui (capacités du modèle) | Aucun ne les lit |
| Donne les prix | Oui | Non | Non | Non (crédits) |
| Donne le coût d'une réponse | Oui | Non | Non | Non |

Détails qui comptent :

- **OpenRouter, OpenAI et 1min.AI partagent un connecteur** parce qu'ils parlent le même
  protocole (« chat completions »). Seules l'adresse et quelques options diffèrent.
- **OpenAI ne dit pas** quels modèles sont des modèles de chat, ni lesquels lisent les images.
  Le connecteur filtre donc sur le nom (`gpt-…`, `o3…`) et exclut les modèles audio, image,
  etc. C'est une heuristique : un futur modèle au nom inhabituel peut manquer.
- **Anthropic a un format différent** : le prompt système est séparé des messages, la taille
  maximale de la réponse est obligatoire (ici le plafond du modèle, sans dépasser 64 000
  tokens), et les images se placent avant le texte. Si un modèle refuse de répondre, le
  connecteur le signale comme une erreur.
- **1min.AI** ([sa documentation](https://docs.1min.ai/docs/api/openai-compatible)) a ses
  propres règles :
  - tous ses modèles sont en texte seul, même ceux dont le nom contient « vl » ;
  - il demande de ne jamais relancer une requête échouée, car chaque essai réserve des
    crédits : le connecteur ne fait aucune nouvelle tentative ;
  - une coupure peut fermer le flux sans message d'erreur : une réponse qui s'arrête sans
    l'indication de fin est signalée comme interrompue ;
  - une requête est limitée à 100 000 caractères et 200 messages. Au-delà, il la refuse, et
    l'application affiche sa raison ;
  - la réponse est plafonnée par défaut à 4 096 tokens ;
  - la consommation est comptée en tokens, la facturation en crédits : l'application
    affiche les tokens, sans coût en dollars.

### 6.5 Le catalogue de modèles (`services/catalog.py`)

Deux régimes, parce que les fournisseurs ne fonctionnent pas pareil :

- **OpenRouter** : son catalogue est public et identique pour tous. Une tâche de fond le
  télécharge au démarrage puis toutes les 30 minutes, et le garde en mémoire pour tous les
  utilisateurs. Si un rafraîchissement échoue, la dernière liste connue reste servie.
- **OpenAI, Anthropic et 1min.AI** : la liste dépend de la clé. Elle est lue à la demande avec la clé de
  l'utilisateur, puis gardée une heure. Elle est oubliée dès qu'il change de clé.

Le réglage `free_only` s'applique à la lecture : la liste OpenRouter d'un utilisateur est le
catalogue complet, moins les modèles payants s'il ne les a pas autorisés. La même fonction sert
à **afficher** les modèles et à **vérifier** qu'un modèle demandé est permis. Un utilisateur ne
peut donc pas utiliser un modèle payant en forgeant une requête.

### 6.6 Les routes de l'API (`routers/`)

| Méthode | Route | Rôle |
| --- | --- | --- |
| GET | `/api/health` | Le serveur répond-il ? |
| GET | `/api/auth/config` | Inscriptions ouvertes ? Mode démonstration ? |
| POST | `/api/auth/register` | Créer un compte |
| POST | `/api/auth/login` | Se connecter |
| POST | `/api/auth/logout` | Se déconnecter |
| GET | `/api/auth/me` | Qui suis-je ? |
| POST | `/api/auth/password` | Changer de mot de passe |
| POST | `/api/auth/delete-account` | Supprimer son compte |
| GET | `/api/keys` | État des clés, pour les trois fournisseurs |
| PUT | `/api/keys/{fournisseur}` | Enregistrer ou remplacer une clé |
| PATCH | `/api/keys/{fournisseur}` | Régler « gratuits uniquement » (OpenRouter) |
| DELETE | `/api/keys/{fournisseur}` | Supprimer une clé |
| GET | `/api/models` | Modèles disponibles, par fournisseur |
| GET | `/api/conversations` | Liste des conversations |
| GET | `/api/conversations/{id}` | Une conversation et ses messages |
| PATCH | `/api/conversations/{id}` | Renommer |
| DELETE | `/api/conversations/{id}` | Supprimer |
| POST | `/api/attachments` | Envoyer un fichier |
| GET | `/api/attachments/{id}` | Récupérer un fichier (pour afficher une image) |
| DELETE | `/api/attachments/{id}` | Retirer un fichier pas encore envoyé |
| POST | `/api/chat` | Envoyer un message, recevoir la réponse en flux |
| POST | `/api/conversations/{id}/regenerate` | Refaire la dernière réponse |
| POST | `/api/conversations/{id}/messages/{message_id}/edit` | Modifier une question |

Toute route autre que `/api/…` renvoie l'interface compilée, quand elle existe : c'est ainsi
qu'en production un seul serveur sert tout.

FastAPI génère aussi une documentation interactive de ces routes sur `/docs`.

### 6.7 Le chat et le streaming (`routers/chat.py`)

Les trois routes de génération (envoyer, régénérer, modifier) suivent le même déroulé :

1. **Vérifier**, avant d'écrire quoi que ce soit : le fournisseur existe, l'utilisateur a une
   clé, le modèle est autorisé, les pièces jointes lui appartiennent et le modèle sait les
   lire. Un refus à ce stade est une erreur HTTP ordinaire, et rien n'est modifié.
2. **Écrire** en base ce que l'utilisateur vient de faire : nouvelle question, question
   modifiée, ou suppression de l'ancienne réponse.
3. **Répondre en flux.** La réponse HTTP reste ouverte et envoie des événements au format SSE :

| Événement | Contenu | Moment |
| --- | --- | --- |
| `start` | La conversation, et la question telle qu'enregistrée | Une fois, au début |
| `delta` | Un morceau de texte | À chaque morceau reçu du fournisseur |
| `error` | Code et message | Si le fournisseur échoue |
| `done` | La réponse telle qu'enregistrée, ou rien | Une fois, à la fin |

4. **Enregistrer la réponse**, dans tous les cas : fin normale, erreur en cours de route, ou
   navigateur qui coupe la connexion (bouton Stop, onglet fermé). Une réponse partielle est
   donc conservée.

Le modèle n'a pas de mémoire : à chaque message, **toute la conversation** lui est renvoyée.
C'est la fonction `_history` qui la reconstitue, pièces jointes comprises.

### 6.8 Les pièces jointes (`attachments.py`, `routers/attachments.py`)

L'envoi se fait en deux temps : le fichier est d'abord envoyé seul et reçoit un identifiant,
puis le message part avec la liste des identifiants à joindre. On peut ainsi valider chaque
fichier et afficher son état avant l'envoi du message.

| Famille | Types | Ce qui est gardé | Comment c'est transmis au modèle |
| --- | --- | --- | --- |
| Image | PNG, JPEG, GIF, WebP | Le fichier tel quel | En image, aux modèles qui les lisent |
| Document | PDF, fichiers texte | Le texte seulement | Inséré dans le message, entre balises `<fichier nom="…">` |

- Le **type est déterminé par le contenu**, pas par le nom ni par ce qu'annonce le navigateur :
  les premiers octets d'un fichier identifient une image. Le SVG n'est volontairement pas
  traité comme une image, car il peut contenir des scripts.
- Les documents fonctionnent avec **tous les modèles**, puisque c'est du texte.
- Les **limites** : 5 Mo par image, 10 Mo par fichier, 200 000 caractères de texte par
  document, 5 fichiers par message. Un document trop long est refusé plutôt que tronqué, pour
  que le modèle ne réponde pas sur un document incomplet sans le dire.
- Un PDF scanné (sans texte) est refusé avec une explication : il n'y a pas de reconnaissance
  de caractères.
- Si l'utilisateur change pour un modèle qui ne lit pas les images en cours de conversation,
  les images des messages précédents sont remplacées par une note, et la conversation continue.
- Un fichier envoyé mais jamais joint est supprimé au bout de 24 heures.

### 6.9 Tokens et coût

À la fin d'une réponse, le connecteur transmet la consommation : tokens en entrée, tokens en
sortie, et parfois le coût. Le coût enregistré suit cet ordre de priorité :

1. le coût annoncé par le fournisseur (OpenRouter le donne) ;
2. zéro si le modèle est gratuit ;
3. un calcul à partir des prix du catalogue, quand ils sont connus ;
4. sinon, rien.

OpenAI et Anthropic ne publient pas leurs prix par leur API, et 1min.AI facture en crédits :
pour eux, l'application affiche les tokens sans le coût. Coder les prix en dur les rendrait faux au premier changement de
tarif.

---

## 7. Le frontend en détail

### 7.1 Deux sortes d'état

L'interface distingue ce qui appartient au serveur de ce qui n'existe que dans le navigateur.

| | Géré par | Exemples |
| --- | --- | --- |
| **Données du serveur** | TanStack Query (`api/hooks.ts`) | Utilisateur connecté, clés, modèles, conversations, messages |
| **État local** | Zustand (`chat/store.ts`) | Modèle choisi, réponse en cours d'arrivée, erreur, panneaux ouverts, thème |

TanStack Query garde une copie de chaque réponse du serveur, identifiée par une clé
(`['conversation', id]`, `['models']`…). Un composant qui en a besoin la demande par cette
clé : la donnée est chargée une fois, partagée, et rafraîchie quand on l'invalide.

Zustand garde le reste. Le modèle choisi, l'état de la barre latérale et le thème sont
mémorisés dans le navigateur (`localStorage`), pour être retrouvés à la visite suivante.

### 7.2 Les routes

| Adresse | Écran |
| --- | --- |
| `/login`, `/register` | Connexion, inscription (`AuthPage`) |
| `/` | Nouvelle conversation (`ChatPage`) |
| `/c/<id>` | Une conversation (`ChatPage`) |

`App.tsx` protège `/` et `/c/<id>` : sans session, on est renvoyé vers `/login`.

### 7.3 Les composants

| Composant | Rôle |
| --- | --- |
| `Sidebar` | Logo, nouvelle conversation, historique groupé par période, compte, thème |
| `ModelPicker` | Choix du modèle, recherche, badges gratuit/payant, icône « lit les images » |
| `MessageList` | Les messages, la réponse en cours, les erreurs, l'édition d'une question |
| `Markdown` | Affichage d'une réponse : texte mis en forme, blocs de code |
| `Composer` | Zone de saisie, pièces jointes, boutons envoyer et arrêter |
| `ArtifactPanel` | Panneau latéral : code ou aperçu |
| `SettingsDialog` | Réglages : onglet clés API, onglet compte |
| `AccountSettings` | Changement de mot de passe, suppression du compte |
| `DemoBanner` | Bandeau du mode démonstration |
| `Logo`, `CopyButton` | Petites briques réutilisées |

### 7.4 L'envoi d'un message (`chat/actions.ts`)

C'est le fichier central du frontend. Une seule fonction, `run`, sert à envoyer, régénérer et
modifier. Elle :

1. note dans le store qu'une génération commence, avec la question à afficher tout de suite ;
2. ouvre la requête et lit le flux d'événements (`streamSSE` dans `api/client.ts`) ;
3. à `start`, range la conversation et la question dans le cache, et, pour une nouvelle
   conversation, change l'adresse vers `/c/<id>` ;
4. à chaque `delta`, ajoute le texte à la réponse en cours ;
5. à `error`, mémorise le message à afficher ;
6. à `done`, remplace la réponse en cours par la réponse enregistrée.

Le bouton Stop annule la requête. Le serveur s'en aperçoit et enregistre ce qu'il avait déjà
reçu ; l'interface garde le texte affiché, puis se resynchronise avec le serveur.

**Pourquoi pas `EventSource`**, l'outil standard du navigateur pour le SSE ? Parce qu'il ne
sait faire que des requêtes GET sans corps, alors qu'il faut ici envoyer le message. Le flux
est donc lu à la main à partir de `fetch`.

### 7.5 Affichage des réponses et panneau latéral

Les réponses sont du Markdown. `react-markdown` le transforme en éléments React **sans jamais
interpréter le HTML brut** : si un modèle écrit `<script>`, il s'affiche comme du texte.

Les blocs de code reçoivent un traitement à part (`Markdown.tsx`, `chat/artifacts.ts`) :

- un bloc **HTML ou SVG** devient une carte cliquable, qui ouvre le panneau avec un aperçu ;
- un bloc de **15 lignes ou plus** garde son affichage et gagne un bouton pour l'ouvrir dans le
  panneau ;
- les autres s'affichent normalement, avec un bouton copier.

L'aperçu exécute du code produit par un modèle : il tourne dans une `iframe` avec l'attribut
`sandbox="allow-scripts"`, **sans** `allow-same-origin`. Le navigateur lui donne alors une
origine à part : ses scripts fonctionnent, mais ils n'ont accès ni au cookie de session, ni au
stockage, ni à l'API de l'application.

### 7.6 Apparence

- **Couleurs** : définies une fois dans `index.css` sous forme de variables, avec un jeu pour
  le thème clair et un pour le sombre. Les composants n'utilisent que ces noms (`bg-surface`,
  `text-muted`, `bg-accent`…), jamais une couleur en dur.
- **Thème** : clair, sombre, ou celui du système. Un petit script dans `index.html` l'applique
  avant le premier affichage, pour éviter un flash.
- **Logo** : `public/logo-mark.png` sert de masque. Le composant `Logo` peint la couleur
  d'accent à travers, ce qui lui fait suivre le thème. Les icônes (favicon, écran d'accueil
  mobile) sont générées par `branding/make_icons.py` à partir du fichier d'origine.
- **Petits écrans** : sous 768 pixels de large, la barre latérale passe par-dessus le contenu ;
  sous 1 024 pixels, le panneau latéral occupe tout l'écran.

---

## 8. Le trajet d'un message, étape par étape

Alice, connectée, écrit « Résume ce document » avec un PDF joint, sur un modèle gratuit
d'OpenRouter.

1. **Elle choisit le PDF.** `Composer` l'envoie aussitôt à `POST /api/attachments`. Le serveur
   reconnaît un PDF à ses premiers octets, en extrait le texte avec `pypdf`, vérifie les
   limites, l'enregistre sans message, et renvoie son identifiant. La pastille du fichier passe
   de « envoi » à « prêt ».
2. **Elle appuie sur Entrée.** `sendMessage` affiche tout de suite sa question, puis appelle
   `POST /api/chat` avec le texte, l'identifiant du fichier, le fournisseur et le modèle.
3. **Le serveur identifie Alice** par son cookie : signature du jeton, version de session.
4. **Il vérifie ses droits** : elle a une clé OpenRouter, il la déchiffre ; le modèle est dans
   son catalogue, et il est gratuit ; le fichier lui appartient et n'a pas déjà servi.
5. **Il enregistre** la conversation (titre : le début de la question), la question, et
   rattache le fichier à cette question.
6. **Il reconstitue la conversation** à envoyer : le texte du PDF est inséré avant la question,
   entre balises `<fichier>`.
7. **Il ouvre le flux** vers le navigateur et envoie `start`. L'interface range la conversation
   dans son cache et passe à l'adresse `/c/<id>`.
8. **Il appelle OpenRouter** avec la clé d'Alice, en demandant une réponse en flux et le
   décompte des tokens.
9. **Chaque morceau** reçu d'OpenRouter repart aussitôt vers le navigateur en `delta`. Le texte
   s'affiche au fur et à mesure.
10. **À la fin**, OpenRouter donne la consommation. Le serveur enregistre la réponse, ses
    tokens et son coût (zéro : modèle gratuit), puis envoie `done`.
11. **L'interface** remplace le texte en cours par le message enregistré. Dessous apparaissent
    le nom du modèle, « 1 234 tokens · gratuit », et les boutons copier et régénérer.

Si OpenRouter avait répondu « trop de requêtes » à l'étape 8, le serveur aurait envoyé `error`
avec un message en français, et la question serait restée enregistrée, avec un bouton
« Réessayer ».

---

## 9. Sécurité

| Risque | Parade |
| --- | --- |
| Vol des clés API en cas de fuite de la base | Clés chiffrées (Fernet) ; la clé de chiffrement est dans `.env`, pas dans la base |
| Fuite d'une clé vers le navigateur | L'API ne renvoie jamais une clé, seulement ses 4 derniers caractères |
| Vol des mots de passe | Empreintes Argon2, jamais le mot de passe |
| Devinette de mot de passe | Limitation des tentatives par adresse et par compte |
| Vol de session par un script | Cookie `HttpOnly` |
| Requête forgée depuis un autre site (CSRF) | Cookie `SameSite=Lax`, corps en JSON |
| Lire les données d'un autre utilisateur | Toute requête est filtrée par l'utilisateur de la session ; une ressource d'autrui répond « introuvable » |
| Utiliser un modèle payant sans l'avoir autorisé | Vérifié par le serveur à chaque message |
| Script injecté par la réponse d'un modèle | Markdown rendu sans HTML brut |
| Code malveillant dans un aperçu HTML | `iframe` isolée, sans accès à la session |
| Fichier piégé | Type déterminé par le contenu, SVG exclu des images, fichiers servis avec une politique qui interdit toute exécution |
| Site tiers qui affiche l'app dans un cadre | En-têtes `X-Frame-Options: DENY` et `frame-ancestors 'none'` |
| Écoute du trafic | HTTPS par Caddy, HSTS, cookie `Secure` |
| Session volée qui reste valide | Changer de mot de passe invalide toutes les autres sessions |

**Ce que le serveur ne peut pas empêcher.** Pendant un échange, la clé d'un utilisateur est
déchiffrée en mémoire pour appeler le fournisseur. Quelqu'un qui contrôle le serveur, ou qui
possède à la fois la base et `FERNET_KEY`, peut lire les clés. C'est inhérent à ce modèle : les
utilisateurs font confiance à l'opérateur du service.

**Sauvegarde.** Deux choses sont irremplaçables : le fichier de base, et `FERNET_KEY`. Sans la
seconde, les clés enregistrées sont illisibles.

---

## 10. Tests

138 tests côté serveur, lancés par `uv run pytest` dans `backend/`. Aucun n'appelle un service
extérieur.

| Fichier | Ce qui est vérifié |
| --- | --- |
| `test_auth.py` | Inscription, connexion, cookie, mots de passe refusés, inscriptions fermées |
| `test_account.py` | Changement de mot de passe, déconnexion des autres sessions, suppression du compte |
| `test_ratelimit.py` | Blocages, déblocage avec le temps, en-têtes de sécurité |
| `test_keys.py` | Clé vérifiée, chiffrée, jamais renvoyée ; cloisonnement entre utilisateurs |
| `test_models.py` | Modèles gratuits par défaut, caches, catalogue conservé en cas de panne |
| `test_providers.py` | Les trois connecteurs réels face à des réponses HTTP simulées |
| `test_chat.py` | Streaming, erreurs, réponse partielle conservée, régénération |
| `test_conversations.py` | Liste, renommage, suppression, cloisonnement |
| `test_edit.py` | Modification d'une question, refus, cloisonnement |
| `test_usage.py` | Tokens et coût, pour chaque cas de calcul |
| `test_attachments.py` | Types acceptés et refusés, limites, transmission aux modèles, suppressions |
| `test_onemin.py` | Connecteur 1min.AI : adresse, aucune relance, erreurs, flux coupé, modèles |
| `test_migrations.py` | Migrations fidèles aux modèles, reprise d'une ancienne base |
| `test_health.py` | Le serveur répond |

Deux techniques se complètent :

- pour tester **l'application**, les fournisseurs sont remplacés par des faux
  (`FakeProvider` dans `conftest.py`), dont on règle les réponses et les pannes ;
- pour tester **les connecteurs**, on garde le vrai code et les vrais SDK, et on simule
  seulement le réseau. On vérifie ainsi la requête réellement envoyée (adresse, en-têtes,
  corps) et la lecture de la réponse.

La base de test vit en mémoire et est recréée avant chaque test.

**Côté interface, il n'y a pas de tests automatisés.** La compilation TypeScript
(`pnpm build`) et le lint (`pnpm lint`) attrapent les erreurs de types et de syntaxe. Le
comportement a été vérifié à la main dans un navigateur, à chaque fonctionnalité, contre le
serveur de démonstration.

---

## 11. Outillage : développement, démo, CI, Docker, git

### Développement

| | Commande (depuis le dossier indiqué) | Adresse |
| --- | --- | --- |
| Backend | `backend/` : `uv run uvicorn app.main:app --reload --port 8642` | <http://localhost:8642> |
| Frontend | `frontend/` : `pnpm dev` | <http://localhost:5180> |

On travaille sur le port 5180. Les ports habituels (8000, 5173) ont été évités parce que
Docker les occupait sur la machine de développement.

### Serveur de démonstration

`backend/scripts/demo_server.py` lance l'application avec des fournisseurs simulés : aucune
clé réelle, aucun appel réseau, une base recréée à chaque démarrage, un compte et des clés
factices déjà en place. Il sert à essayer et à tester l'interface. Un bandeau le signale à
l'écran, car les vraies clés n'y fonctionnent pas.

### Intégration continue

`.github/workflows/ci.yml` lance, à chaque push sur `main` ou `develop` et à chaque pull
request :

- backend : installation verrouillée, `ruff check`, `ruff format --check`, `pytest` ;
- frontend : installation verrouillée, `pnpm lint`, `pnpm build`.

### Docker

Le `Dockerfile` procède en deux étapes : une image Node compile l'interface, puis une image
Python reçoit le backend et l'interface compilée. Le conteneur tourne avec un utilisateur sans
privilèges, et la base est dans un volume.

`compose.yaml` assemble deux services : l'application, non exposée, et Caddy, qui écoute sur
les ports 80 et 443, obtient le certificat pour le domaine indiqué dans `DOMAIN`, et relaie
vers l'application.

### Git

Le dépôt suit **git-flow** :

- `main` : les versions publiées ;
- `develop` : l'intégration ;
- `feature/<nom>` : une branche par évolution, nommée en français, fusionnée dans `develop`
  avec un commit de fusion.

Les fonctionnalités, dans l'ordre où elles ont été construites :

| Feature | Contenu |
| --- | --- |
| `squelette` | Projets backend et frontend vides, outils |
| `authentification` | Comptes, sessions, modèle de données |
| `fournisseurs` | Les trois connecteurs, clés chiffrées, catalogue |
| `api-chat` | Conversations, streaming, régénération |
| `interface-chat` | Toute l'interface de base |
| `artefacts` | Panneau latéral, thème sombre, mobile |
| `documentation` | README |
| `logo` | Logo et icônes |
| `bandeau-demo` | Signalement du mode démonstration |
| `migrations` | Alembic |
| `durcissement-connexion` | Limitation des tentatives, en-têtes de sécurité |
| `gestion-compte` | Mot de passe, suppression du compte |
| `integration-continue` | GitHub Actions |
| `docker` | Image et déploiement |
| `cout-par-reponse` | Tokens et coût |
| `modifier-message` | Édition d'une question |
| `pieces-jointes` | Images et fichiers |
| `synthese-projet` | Ce document |
| `fournisseur-1min` | Quatrième fournisseur : 1min.AI |

---

## 12. Décisions et compromis

**SQLite plutôt que PostgreSQL.** Un fichier, rien à administrer, et largement assez pour des
milliers d'utilisateurs occasionnels. La contrepartie : un seul écrivain à la fois, donc une
seule instance du serveur. Comme le code passe par SQLAlchemy, changer de base plus tard
reviendrait surtout à changer `DATABASE_URL`.

**Un seul processus.** Le compteur de tentatives, le catalogue et les caches vivent en mémoire.
C'est simple et rapide, mais cela interdit de lancer plusieurs instances derrière un
répartiteur. Pour monter en charge, il faudrait déplacer ces états dans un service partagé.

**Les fichiers joints dans la base.** Ils sont stockés dans SQLite et non sur disque. Une seule
chose à sauvegarder, et les suppressions se propagent toutes seules. La contrepartie : la base
grossit avec les images.

**Une session par jeton signé, sans table de sessions.** Le serveur n'a rien à stocker pour
savoir qui est connecté. La révocation, qu'un jeton pur ne permet pas, est obtenue par le
compteur `token_version`.

**SSE plutôt que WebSocket.** La réponse ne va que dans un sens, du serveur vers le navigateur.
Une réponse HTTP en flux suffit, traverse les proxys sans réglage, et se teste comme une
requête ordinaire.

**Le titre d'une conversation n'est pas généré par un modèle.** Il reprend le début de la
première question. Un appel de plus par conversation entamerait le quota des modèles gratuits.

**Pas de politique de contenu stricte sur les scripts.** L'aperçu des pages générées exécute
leurs scripts dans une `iframe` qui hérite de la politique de la page : l'interdire casserait
l'aperçu. La protection repose sur l'isolement de cette `iframe` et sur le rendu du Markdown
sans HTML.

**Pas de bascule automatique quand un modèle Anthropic refuse de répondre.** L'utilisateur a
choisi son modèle ; l'application affiche le refus plutôt que de répondre avec un autre.

**Les SDK officiels plutôt que des requêtes HTTP écrites à la main.** Ils suivent les
évolutions des API et gèrent les reprises sur erreur. `httpx` ne sert que pour deux endpoints
d'OpenRouter qui n'existent dans aucun SDK.

---

## 13. Limites connues et suites possibles

### Ce qui n'a pas été vérifié en conditions réelles

- **OpenAI, Anthropic et 1min.AI avec de vraies clés.** Leurs connecteurs sont testés contre
  des réponses simulées. Seul OpenRouter a été utilisé pour de vrai, avec des modèles
  gratuits. Pour 1min.AI, seul le rejet d'une fausse clé par sa vraie API a été vérifié.
- **Le déploiement HTTPS.** L'image Docker a tourné en local, pièces jointes comprises, et les
  fichiers de configuration sont valides, mais Caddy n'a jamais obtenu de certificat pour un
  vrai domaine.
- **La CI.** Le fichier est écrit, mais ne s'exécutera qu'une fois poussé sur GitHub.
- **Le format exact du coût chez OpenRouter.** La lecture du champ `cost` est testée contre une
  réponse simulée ; si OpenRouter ne le renvoie pas, le coût est calculé d'après le catalogue.

### Ce qui manque pour une ouverture large

- **Mot de passe oublié et vérification de l'e-mail** : il faut un service d'envoi d'e-mails.
  Sans cela, un mot de passe oublié fait perdre le compte.
- **Mentions légales et politique de confidentialité** : l'application stocke des e-mails et
  des conversations.
- **Sauvegardes automatiques** de la base.
- **Limites par utilisateur** : rien ne plafonne le nombre de conversations ni l'espace occupé
  par les fichiers joints.

### Limites fonctionnelles

- **Pas de gestion de la taille de contexte.** Toute la conversation est renvoyée à chaque
  message. Une très longue conversation finit par dépasser ce que le modèle accepte, et le
  fournisseur renvoie alors une erreur.
- **PDF scannés** non lus (pas de reconnaissance de caractères).
- **Modifier une question efface la suite**, sans garder l'ancienne version.
- **Pas de recherche** dans les conversations, **pas de prompt système** ni de personas.
- **Coût inconnu** pour OpenAI, Anthropic et 1min.AI.
- **Pas de tests automatisés de l'interface.**

---

## 14. Glossaire

| Terme | Définition |
| --- | --- |
| **API** | Ensemble de requêtes qu'un programme propose aux autres. Ici : celle du serveur pour l'interface, et celles des fournisseurs pour le serveur |
| **Argon2** | Algorithme qui transforme un mot de passe en empreinte, volontairement lent pour décourager les essais en masse |
| **ASGI** | Convention entre un serveur web Python et une application asynchrone. Uvicorn l'implémente, FastAPI la respecte |
| **BYOK** | *Bring your own key* : l'utilisateur fournit sa propre clé API |
| **Clé API** | Chaîne secrète qui identifie un compte auprès d'un fournisseur, et sur laquelle l'usage est facturé |
| **Cookie** | Petite donnée que le serveur confie au navigateur, renvoyée à chaque requête |
| **CORS** | Règles du navigateur sur les requêtes entre sites différents. Évitées ici : interface et API ont la même origine |
| **CSRF** | Attaque où un autre site fait agir le navigateur de la victime sur l'application à son insu |
| **Fernet** | Format de chiffrement symétrique : la même clé chiffre et déchiffre, et toute altération est détectée |
| **Hook** | Fonction React dont le nom commence par `use`, qui donne à un composant un état ou une donnée |
| **JWT** | Jeton signé : son contenu est lisible, mais ne peut pas être modifié sans la clé de signature |
| **Markdown** | Syntaxe légère de mise en forme (`**gras**`, listes, blocs de code) dans laquelle les modèles répondent |
| **Middleware** | Code exécuté autour de chaque requête. Ici : l'ajout des en-têtes de sécurité |
| **Migration** | Script qui fait passer la base d'une version de son schéma à la suivante |
| **ORM** | Bibliothèque qui fait correspondre des tables à des classes. Ici : SQLModel |
| **Origine** | Le trio protocole, nom de domaine, port. Le navigateur cloisonne les sites par origine |
| **Prompt système** | Instruction donnée au modèle avant la conversation, pour fixer son comportement |
| **Reverse proxy** | Serveur placé devant l'application, qui reçoit les requêtes à sa place. Ici : Caddy |
| **SDK** | Bibliothèque fournie par un service pour l'utiliser depuis un langage donné |
| **SSE** | *Server-sent events* : une réponse HTTP qui reste ouverte et envoie des événements au fil de l'eau |
| **Streaming** | Recevoir la réponse par morceaux, au lieu d'attendre qu'elle soit complète |
| **Token** | Unité de texte pour un modèle : un mot court, ou un morceau de mot. Les limites et les prix se comptent en tokens |
| **XSS** | Attaque où du code injecté s'exécute dans la page d'un autre utilisateur |
