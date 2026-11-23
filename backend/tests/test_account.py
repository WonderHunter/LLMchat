from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine
from app.main import app
from app.models import Conversation, Message, ProviderKey, User
from app.ratelimit import login_failures_by_email
from tests.conftest import PASSWORD, add_key
from tests.test_chat import send

NEW_PASSWORD = "nouveau-mot-de-passe-42"


def login(client, password):
    return client.post("/api/auth/login", json={"email": "alice@example.com", "password": password})


def change_password(client, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        "/api/auth/password", json={"current_password": current, "new_password": new}
    )


def test_account_actions_require_authentication(client):
    assert change_password(client).status_code == 401
    assert client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 401


def test_change_password(client, user):
    assert change_password(client).status_code == 204
    # La session qui a fait le changement reste ouverte.
    assert client.get("/api/auth/me").status_code == 200

    client.post("/api/auth/logout")
    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_change_password_needs_the_current_one_and_a_long_enough_new_one(client, user):
    assert change_password(client, current="pas-le-bon").status_code == 403
    assert change_password(client, new="court").status_code == 422
    client.post("/api/auth/logout")
    assert login(client, PASSWORD).status_code == 200


def test_change_password_closes_the_other_sessions(client, user):
    with TestClient(app) as other_device:
        assert login(other_device, PASSWORD).status_code == 200
        assert other_device.get("/api/auth/me").status_code == 200

        change_password(client)

        assert other_device.get("/api/auth/me").status_code == 401
        assert other_device.get("/api/conversations").status_code == 401
    assert client.get("/api/auth/me").status_code == 200


def test_wrong_current_password_is_rate_limited(client, user):
    for _ in range(login_failures_by_email.limit):
        assert change_password(client, current="pas-le-bon").status_code == 403
    assert change_password(client).status_code == 429


def test_delete_account_removes_everything_that_belongs_to_it(
    client, providers, user, other_client
):
    add_key(client)
    add_key(other_client)
    send(client, "À effacer")
    send(other_client, "À garder")

    refused = client.post("/api/auth/delete-account", json={"password": "pas-le-bon"})
    assert refused.status_code == 403
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert login(client, PASSWORD).status_code == 401

    with Session(engine) as session:
        assert [u.email for u in session.exec(select(User))] == ["bob@example.com"]
        assert len(session.exec(select(ProviderKey)).all()) == 1
        assert len(session.exec(select(Conversation)).all()) == 1
        assert {m.content for m in session.exec(select(Message))} == {"À garder", "Bonjour !"}
    # Le compte de Bob n'est pas touché.
    assert len(other_client.get("/api/conversations").json()) == 1


def test_email_can_be_registered_again_after_deletion(client, user):
    client.post("/api/auth/delete-account", json={"password": PASSWORD})
    again = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert again.status_code == 201
