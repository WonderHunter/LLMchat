"""Serveur de démonstration : fournisseurs simulés, aucune vraie clé, aucun appel réseau.

Sert à essayer l'interface sans consommer de quota. Depuis backend/ :

    uv run python scripts/demo_server.py

La base demo.db est recréée à chaque démarrage, avec le compte ci-dessous et une clé
factice par fournisseur. Dans les réglages, toute clé commençant par « demo- » est acceptée.
Un message contenant le mot « erreur » simule une panne du fournisseur en cours de réponse.
"""

import asyncio
import os
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEMO_DB = BACKEND_DIR / "demo.db"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-llmchat-2026"
DEMO_KEY = "demo-key-0000"

sys.path.insert(0, str(BACKEND_DIR))
DEMO_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DEMO_DB.as_posix()}"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["CATALOG_REFRESH_MINUTES"] = "0"
os.environ["DEMO_MODE"] = "true"

import uvicorn  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ProviderKey, User  # noqa: E402
from app.providers.base import InvalidKey, ModelInfo, Provider, QuotaExceeded  # noqa: E402
from app.providers.registry import PROVIDERS  # noqa: E402
from app.security import encrypt_secret, hash_password  # noqa: E402

REPLY = """Voici une réponse **simulée** à : « {question} ».

Ce que montre cette démonstration :

- le texte arrive mot par mot ;
- le Markdown est mis en forme, y compris les `extraits de code` ;
- les blocs de code sont colorés et peuvent être copiés.

```python
def fibonacci(n: int) -> list[int]:
    suite = [0, 1]
    while len(suite) < n:
        suite.append(suite[-1] + suite[-2])
    return suite[:n]


print(fibonacci(10))
```

Et une petite page à ouvrir dans le panneau latéral :

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8" />
    <style>
      body {{ font-family: system-ui; display: grid; place-items: center; height: 100vh; margin: 0;
             background: #faf9f5; color: #1f1e1b; }}
      button {{ font-size: 1.2rem; padding: 0.6rem 1.4rem; border: 0; border-radius: 999px;
               background: #c96442; color: white; cursor: pointer; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Compteur</h1>
      <button id="plus">Cliqué 0 fois</button>
    </main>
    <script>
      let total = 0
      const bouton = document.getElementById('plus')
      bouton.addEventListener('click', () => {{
        total += 1
        bouton.textContent = `Cliqué ${{total}} fois`
      }})
    </script>
  </body>
</html>
```

| Fournisseur | Modèle utilisé |
| --- | --- |
| {provider} | `{model}` |
"""


class DemoProvider(Provider):
    keys_url = "https://example.com/"

    def __init__(self, provider_id: str, label: str, models: list[ModelInfo]):
        self.id = provider_id
        self.label = label
        self.models = models

    async def validate_key(self, key):
        if not key.startswith("demo-"):
            raise InvalidKey(self.label)

    async def list_models(self, key):
        return self.models

    async def stream_chat(self, key, model, messages):
        question = messages[-1]["content"]
        reply = REPLY.format(question=question[:80], provider=self.label, model=model.id)
        pieces = reply.split(" ")
        await asyncio.sleep(0.6)
        for index, piece in enumerate(pieces):
            if "erreur" in question.lower() and index == 12:
                raise QuotaExceeded(self.label)
            yield piece if index == len(pieces) - 1 else piece + " "
            await asyncio.sleep(0.025)


DEMO_PROVIDERS = [
    DemoProvider(
        "openrouter",
        "OpenRouter",
        [
            ModelInfo(id="demo/eclair:free", name="Démo : Éclair (free)", free=True),
            ModelInfo(id="demo/brise:free", name="Démo : Brise (free)", free=True),
            ModelInfo(id="demo/titan", name="Démo : Titan", input_price=3.0, output_price=15.0),
        ],
    ),
    DemoProvider("openai", "OpenAI", [ModelInfo(id="gpt-demo", name="gpt-demo")]),
    DemoProvider("anthropic", "Anthropic", [ModelInfo(id="claude-demo", name="Claude Démo")]),
]


def seed() -> None:
    init_db()
    with Session(engine) as session:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        session.add(user)
        session.flush()
        for provider in DEMO_PROVIDERS:
            session.add(
                ProviderKey(
                    user_id=user.id,
                    provider=provider.id,
                    key_enc=encrypt_secret(DEMO_KEY),
                    last4=DEMO_KEY[-4:],
                )
            )
        session.commit()


if __name__ == "__main__":
    for demo in DEMO_PROVIDERS:
        PROVIDERS[demo.id] = demo
    seed()
    print(f"Compte de démonstration : {DEMO_EMAIL} / {DEMO_PASSWORD}")
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8642")))
