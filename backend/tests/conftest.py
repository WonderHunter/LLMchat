import os

from cryptography.fernet import Fernet

# À définir avant tout import de l'application : la config est lue à l'import.
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["CATALOG_REFRESH_MINUTES"] = "0"
os.environ.pop("OPENROUTER_SERVICE_KEY", None)
os.environ.pop("DEMO_MODE", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.base import InvalidKey, ModelInfo, Provider, Usage  # noqa: E402
from app.providers.registry import PROVIDERS  # noqa: E402
from app.ratelimit import ALL_LIMITERS  # noqa: E402
from app.services.catalog import catalog  # noqa: E402

PASSWORD = "correct-horse-battery"
VALID_KEY = "sk-test-valide-1234"


class FakeProvider(Provider):
    """Fournisseur simulé : aucune requête réseau."""

    keys_url = "https://example.com/keys"

    def __init__(self, provider_id: str, models: list[ModelInfo]):
        self.id = provider_id
        self.label = provider_id.capitalize()
        self.models = models
        self.chunks = ["Bon", "jour", " !"]
        self.usage: Usage | None = Usage(input_tokens=12, output_tokens=34)
        self.error: Exception | None = None  # échec de list_models
        self.chat_error: Exception | None = None  # échec pendant stream_chat
        self.list_calls = 0
        self.chat_calls: list[dict] = []

    async def validate_key(self, key):
        if key != VALID_KEY:
            raise InvalidKey(self.label)

    async def list_models(self, key):
        self.list_calls += 1
        if self.error:
            raise self.error
        return self.models

    async def stream_chat(self, key, model, messages):
        self.chat_calls.append({"key": key, "model": model, "messages": messages})
        for chunk in self.chunks:
            yield chunk
        if self.chat_error:
            raise self.chat_error
        if self.usage:
            yield self.usage


@pytest.fixture
def providers(monkeypatch) -> dict[str, FakeProvider]:
    fakes = {
        "openrouter": FakeProvider(
            "openrouter",
            [
                ModelInfo(id="acme/petit:free", name="Petit (free)", free=True),
                ModelInfo(id="acme/grand", name="Grand", input_price=3.0, output_price=15.0),
            ],
        ),
        "openai": FakeProvider("openai", [ModelInfo(id="gpt-test", name="gpt-test")]),
        "anthropic": FakeProvider(
            "anthropic", [ModelInfo(id="claude-test", name="Claude Test", max_output_tokens=8000)]
        ),
    }
    for provider_id, fake in fakes.items():
        monkeypatch.setitem(PROVIDERS, provider_id, fake)
    return fakes


def reset_database() -> None:
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")


@pytest.fixture
def client():
    reset_database()
    catalog.clear()
    for limiter in ALL_LIMITERS:
        limiter.clear()
    with TestClient(app) as test_client:
        yield test_client


def add_key(client: TestClient, provider: str = "openrouter") -> dict:
    response = client.put(f"/api/keys/{provider}", json={"key": VALID_KEY})
    assert response.status_code == 200, response.text
    return response.json()


def register(client: TestClient, email: str = "alice@example.com") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def user(client):
    return register(client)


@pytest.fixture
def other_client(client):
    """Un second navigateur, connecté avec un autre compte."""
    with TestClient(app) as second:
        register(second, "bob@example.com")
        yield second
