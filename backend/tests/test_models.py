import asyncio

import pytest

from app.providers.base import ModelInfo, ProviderError, ProviderUnavailable
from app.services.catalog import catalog
from tests.conftest import add_key


def models_of(client, provider: str) -> list[str]:
    entries = {e["provider"]: e for e in client.get("/api/models").json()}
    return [m["id"] for m in entries[provider]["models"]]


def test_no_key_means_no_models(client, providers, user):
    assert client.get("/api/models").json() == []


def test_only_providers_with_a_key_are_listed(client, providers, user):
    add_key(client, "anthropic")
    assert [e["provider"] for e in client.get("/api/models").json()] == ["anthropic"]


def test_openrouter_is_limited_to_free_models_by_default(client, providers, user):
    add_key(client, "openrouter")
    assert models_of(client, "openrouter") == ["acme/petit:free"]

    client.patch("/api/keys/openrouter", json={"free_only": False})
    assert models_of(client, "openrouter") == ["acme/petit:free", "acme/grand"]

    paid = client.get("/api/models").json()[0]["models"][1]
    assert paid["free"] is False
    assert paid["input_price"] == 3.0


def test_openrouter_catalog_is_shared_between_users(client, providers, user, other_client):
    add_key(client, "openrouter")
    add_key(other_client, "openrouter")
    models_of(client, "openrouter")
    models_of(other_client, "openrouter")
    assert providers["openrouter"].list_calls == 1


def test_user_models_are_cached_until_the_key_changes(client, providers, user):
    add_key(client, "openai")
    models_of(client, "openai")
    models_of(client, "openai")
    assert providers["openai"].list_calls == 1

    add_key(client, "openai")
    models_of(client, "openai")
    assert providers["openai"].list_calls == 2


def test_a_failing_provider_does_not_break_the_others(client, providers, user):
    add_key(client, "openai")
    add_key(client, "anthropic")
    providers["openai"].error = ProviderUnavailable("OpenAI")

    entries = {e["provider"]: e for e in client.get("/api/models").json()}
    assert entries["openai"]["models"] == []
    assert "injoignable" in entries["openai"]["error"]
    assert entries["anthropic"]["error"] is None
    assert [m["id"] for m in entries["anthropic"]["models"]] == ["claude-test"]


async def test_catalog_keeps_last_known_list_when_refresh_fails(providers):
    catalog.clear()
    await catalog.refresh_openrouter()
    providers["openrouter"].error = ProviderUnavailable("OpenRouter")

    with pytest.raises(ProviderError):
        await catalog.refresh_openrouter()
    # La boucle de fond, elle, ne doit pas s'arrêter sur cette erreur.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(catalog.run_forever(1), timeout=0.05)

    models = await catalog.models_for(1, "openrouter", "", free_only=False)
    assert [m.id for m in models] == ["acme/petit:free", "acme/grand"]


async def test_catalog_find_respects_free_only(providers):
    catalog.clear()
    assert await catalog.find(1, "openrouter", "", True, "acme/grand") is None
    assert await catalog.find(1, "openrouter", "", False, "acme/grand") == ModelInfo(
        id="acme/grand", name="Grand", input_price=3.0, output_price=15.0
    )
