import pytest

from app.config import get_settings
from app.ratelimit import (
    RateLimiter,
    login_failures_by_email,
    login_failures_by_ip,
    registrations_by_ip,
)
from tests.conftest import PASSWORD, register


class Clock:
    def __init__(self):
        self.time = 1000.0

    def __call__(self) -> float:
        return self.time


def test_limiter_blocks_at_the_limit_then_frees_up_as_time_passes():
    limiter = RateLimiter(limit=2, window_seconds=60)
    limiter.now = clock = Clock()

    limiter.record("a")
    assert limiter.retry_after("a") is None
    clock.time += 10
    limiter.record("a")
    assert limiter.retry_after("a") == 50
    assert limiter.retry_after("b") is None

    clock.time += 50
    assert limiter.retry_after("a") is None


def login(client, email="alice@example.com", password="mauvais-mot-de-passe"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_repeated_wrong_passwords_lock_the_account_even_with_the_right_one(client, user):
    client.post("/api/auth/logout")
    for _ in range(login_failures_by_email.limit):
        assert login(client).status_code == 401

    blocked = login(client, password=PASSWORD)
    assert blocked.status_code == 429
    assert "Trop de tentatives" in blocked.json()["detail"]
    assert int(blocked.headers["retry-after"]) > 0
    assert client.get("/api/auth/me").status_code == 401


def test_other_accounts_stay_reachable_while_one_is_locked(client, user, other_client):
    for _ in range(login_failures_by_email.limit):
        login(client)
    other_client.post("/api/auth/logout")
    assert login(other_client, "bob@example.com", PASSWORD).status_code == 200


def test_successful_login_clears_the_failures_of_that_account(client, user):
    client.post("/api/auth/logout")
    for _ in range(login_failures_by_email.limit - 1):
        login(client)
    assert login(client, password=PASSWORD).status_code == 200
    client.post("/api/auth/logout")
    for _ in range(login_failures_by_email.limit - 1):
        assert login(client).status_code == 401


def test_one_address_cannot_try_many_accounts(client):
    for attempt in range(login_failures_by_ip.limit):
        assert login(client, f"cible{attempt}@example.com").status_code == 401
    assert login(client, "encore@example.com").status_code == 429


def test_lock_ends_after_the_window(client, user, monkeypatch):
    client.post("/api/auth/logout")
    clock = Clock()
    monkeypatch.setattr(login_failures_by_email, "now", clock)
    monkeypatch.setattr(login_failures_by_ip, "now", clock)
    for _ in range(login_failures_by_email.limit):
        login(client)
    assert login(client, password=PASSWORD).status_code == 429

    clock.time += login_failures_by_email.window + 1
    assert login(client, password=PASSWORD).status_code == 200


def test_account_creation_is_limited_per_address(client):
    for index in range(registrations_by_ip.limit):
        register(client, f"compte{index}@example.com")
    response = client.post(
        "/api/auth/register", json={"email": "de-trop@example.com", "password": PASSWORD}
    )
    assert response.status_code == 429


@pytest.mark.parametrize("path", ["/api/health", "/api/auth/me", "/"])
def test_security_headers_are_set_on_every_response(client, path):
    headers = client.get(path).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert "strict-transport-security" not in headers


def test_hsts_is_sent_only_when_served_over_https(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    assert "max-age" in client.get("/api/health").headers["strict-transport-security"]
