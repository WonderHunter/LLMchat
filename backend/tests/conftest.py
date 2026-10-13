import os

from cryptography.fernet import Fernet

# À définir avant tout import de l'application : la config est lue à l'import.
os.environ["SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["FERNET_KEY"] = Fernet.generate_key().decode()
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["CATALOG_REFRESH_MINUTES"] = "0"
os.environ.pop("OPENROUTER_SERVICE_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    SQLModel.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client


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
