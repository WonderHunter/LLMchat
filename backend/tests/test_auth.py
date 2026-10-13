from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.models import User
from app.security import SESSION_COOKIE
from tests.conftest import PASSWORD, register


def test_register_sets_session_and_hashes_password(client):
    user = register(client)
    assert user["email"] == "alice@example.com"
    assert "password" not in user and "password_hash" not in user

    assert client.get("/api/auth/me").json()["email"] == "alice@example.com"

    with Session(engine) as session:
        stored = session.exec(select(User)).one()
    assert stored.password_hash != PASSWORD
    assert stored.password_hash.startswith("$argon2")


def test_session_cookie_is_http_only(client):
    response = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )
    cookie = response.headers["set-cookie"].lower()
    assert SESSION_COOKIE in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_register_rejects_duplicate_email_case_insensitive(client, user):
    response = client.post(
        "/api/auth/register", json={"email": "Alice@Example.com", "password": PASSWORD}
    )
    assert response.status_code == 409


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": "court"}
    )
    assert response.status_code == 422


def test_register_closed(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_registration", False)
    response = client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": PASSWORD}
    )
    assert response.status_code == 403
    assert client.get("/api/auth/config").json() == {"allow_registration": False}


def test_login_logout(client, user):
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    response = client.post(
        "/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_login_rejects_wrong_password_and_unknown_email(client, user):
    client.post("/api/auth/logout")
    wrong = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "mauvais-mot-de-passe"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_rejects_missing_or_forged_cookie(client):
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set(SESSION_COOKIE, "pas.un.jeton")
    assert client.get("/api/auth/me").status_code == 401
