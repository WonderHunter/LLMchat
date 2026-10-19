from sqlmodel import Session, select

from app.db import engine
from app.models import ProviderKey
from app.security import decrypt_secret
from tests.conftest import VALID_KEY, add_key


def test_keys_require_authentication(client, providers):
    assert client.get("/api/keys").status_code == 401
    assert client.put("/api/keys/openrouter", json={"key": VALID_KEY}).status_code == 401


def test_list_shows_every_provider_without_key(client, providers, user):
    keys = {k["provider"]: k for k in client.get("/api/keys").json()}
    assert set(keys) == {"openrouter", "openai", "anthropic", "onemin"}
    assert not any(k["has_key"] for k in keys.values())
    assert keys["openrouter"]["free_only"] is True
    assert keys["openai"]["free_only"] is None


def test_invalid_key_is_rejected_and_not_stored(client, providers, user):
    response = client.put("/api/keys/openai", json={"key": "sk-mauvaise-cle"})
    assert response.status_code == 400
    assert "invalide" in response.json()["detail"]
    with Session(engine) as session:
        assert session.exec(select(ProviderKey)).first() is None


def test_key_is_stored_encrypted_and_never_returned(client, providers, user):
    response = client.put("/api/keys/anthropic", json={"key": f"  {VALID_KEY}  "})
    assert response.status_code == 200
    assert response.json()["has_key"] is True
    assert response.json()["last4"] == VALID_KEY[-4:]

    with Session(engine) as session:
        row = session.exec(select(ProviderKey)).one()
    assert VALID_KEY not in row.key_enc
    assert decrypt_secret(row.key_enc) == VALID_KEY

    for body in (response.text, client.get("/api/keys").text, client.get("/api/models").text):
        assert VALID_KEY not in body


def test_replacing_a_key_keeps_a_single_row(client, providers, user):
    add_key(client, "openai")
    add_key(client, "openai")
    with Session(engine) as session:
        assert len(session.exec(select(ProviderKey)).all()) == 1


def test_free_only_can_be_switched_for_openrouter_only(client, providers, user):
    assert client.patch("/api/keys/openrouter", json={"free_only": False}).status_code == 404

    add_key(client, "openrouter")
    add_key(client, "openai")
    response = client.patch("/api/keys/openrouter", json={"free_only": False})
    assert response.status_code == 200
    assert response.json()["free_only"] is False
    assert client.patch("/api/keys/openai", json={"free_only": False}).status_code == 400


def test_delete_key(client, providers, user):
    add_key(client, "openai")
    assert client.delete("/api/keys/openai").status_code == 204
    keys = {k["provider"]: k for k in client.get("/api/keys").json()}
    assert keys["openai"]["has_key"] is False


def test_unknown_provider(client, providers, user):
    assert client.put("/api/keys/inconnu", json={"key": VALID_KEY}).status_code == 404


def test_keys_are_private_to_each_user(client, providers, user, other_client):
    add_key(client, "openai")
    assert not any(k["has_key"] for k in other_client.get("/api/keys").json())
    assert other_client.get("/api/models").json() == []
