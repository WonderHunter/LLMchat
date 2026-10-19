"""Connecteur 1min.AI, face à des réponses HTTP simulées (aucun appel réseau)."""

import json

import httpx2
import pytest

from app.providers.base import (
    InsufficientCredit,
    InvalidKey,
    ModelInfo,
    ProviderError,
    QuotaExceeded,
    Usage,
)
from app.providers.openai_compat import OneMinProvider
from tests.test_providers import HELLO, collect, sse, usage_of, with_transport

MODEL = ModelInfo(id="mistral-small-latest", name="mistral-small-latest")


def chunk(text: str | None = None, finish: str | None = None) -> str:
    delta = {"content": text} if text is not None else {}
    payload = {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL.id,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def usage_chunk() -> str:
    payload = {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL.id,
        "choices": [],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
    }
    return f"data: {json.dumps(payload)}\n\n"


def onemin(handler) -> OneMinProvider:
    provider = with_transport(OneMinProvider(), handler)
    # Le connecteur ne relance jamais : on garde son réglage, pas celui des autres tests.
    provider.max_retries = OneMinProvider.max_retries
    return provider


def error(status: int, code: str, message: str = "non") -> httpx2.Response:
    body = {"error": {"message": message, "type": "error", "param": None, "code": code}}
    return httpx2.Response(status, json=body)


async def test_chat_goes_to_the_1min_endpoint_with_the_user_key():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return sse(chunk("Bon"), chunk("jour", finish="stop"), usage_chunk(), "data: [DONE]\n\n")

    provider = onemin(handler)
    assert await collect(provider.stream_chat("cle-1min", MODEL, HELLO)) == "Bonjour"

    assert seen["url"] == "https://api.1min.ai/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer cle-1min"
    assert seen["body"]["model"] == MODEL.id
    assert seen["body"]["stream_options"] == {"include_usage": True}
    # Pas de champ propre à OpenRouter.
    assert "usage" not in seen["body"]


async def test_usage_is_read_but_no_dollar_cost_is_invented():
    provider = onemin(
        lambda _r: sse(chunk("Salut", finish="stop"), usage_chunk(), "data: [DONE]\n\n")
    )
    usage = await usage_of(provider.stream_chat("cle", MODEL, HELLO))
    assert usage == Usage(input_tokens=5, output_tokens=2, cost=None)


async def test_a_failed_request_is_never_retried():
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return error(429, "rate_limit_exceeded")

    with pytest.raises(QuotaExceeded):
        await collect(onemin(handler).stream_chat("cle", MODEL, HELLO))
    assert len(calls) == 1


async def test_missing_credits_are_reported_as_such():
    provider = onemin(lambda _r: error(429, "insufficient_quota"))
    with pytest.raises(InsufficientCredit):
        await collect(provider.stream_chat("cle", MODEL, HELLO))


async def test_refused_request_shows_the_reason_given_by_1min():
    provider = onemin(
        lambda _r: error(400, "context_length_exceeded", "Request exceeds 100000 characters.")
    )
    with pytest.raises(ProviderError, match="exceeds 100000 characters"):
        await collect(provider.stream_chat("cle", MODEL, HELLO))


async def test_error_sent_in_the_middle_of_the_stream_is_reported():
    frame = {"error": {"message": "Upstream timeout", "type": "server_error", "code": None}}
    provider = onemin(lambda _r: sse(chunk("Début"), f"data: {json.dumps(frame)}\n\n"))

    received = []
    with pytest.raises(ProviderError, match="Upstream timeout"):
        async for part in provider.stream_chat("cle", MODEL, HELLO):
            received.append(part)
    assert received == ["Début"]


async def test_stream_cut_without_finish_is_reported_after_the_text():
    provider = onemin(lambda _r: sse(chunk("Début"), chunk(" coupé")))
    received = []
    with pytest.raises(ProviderError, match="arrêtée avant la fin"):
        async for part in provider.stream_chat("cle", MODEL, HELLO):
            received.append(part)
    assert received == ["Début", " coupé"]


async def test_models_are_text_only_and_grouped_by_publisher():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.1min.ai/openai/v1/models"
        data = [
            {"id": "gpt-4.1-mini", "object": "model", "created": 1, "owned_by": "openai"},
            {"id": "deepseek-chat", "object": "model", "created": 1, "owned_by": "deepseek"},
            {"id": "qwen-vl-plus", "object": "model", "created": 1, "owned_by": "alibaba"},
        ]
        return httpx2.Response(200, json={"object": "list", "data": data})

    models = await onemin(handler).list_models("cle")
    assert [m.id for m in models] == ["qwen-vl-plus", "deepseek-chat", "gpt-4.1-mini"]
    # Même les modèles « vl » sont servis en texte seul par 1min.AI.
    assert not any(m.accepts_images or m.free for m in models)
    assert all(m.input_price is None for m in models)


async def test_invalid_key_is_refused():
    provider = onemin(lambda _r: error(401, "invalid_api_key", "Invalid or inactive API key."))
    with pytest.raises(InvalidKey):
        await provider.validate_key("mauvaise")


def test_1min_appears_with_its_keys_page(client, providers, user):
    keys = {k["provider"]: k for k in client.get("/api/keys").json()}
    assert keys["onemin"]["label"] == "Onemin"  # libellé du faux fournisseur des tests
    assert OneMinProvider.keys_url == "https://app.1min.ai/api"
    assert OneMinProvider.label == "1min.AI"
