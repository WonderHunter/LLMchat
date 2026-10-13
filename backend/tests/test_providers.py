"""Connecteurs réels, face à des réponses HTTP simulées (aucun appel réseau)."""

import json

import httpx
import httpx2
import pytest
import respx

from app.providers.anthropic import AnthropicProvider
from app.providers.base import (
    InsufficientCredit,
    InvalidKey,
    ModelInfo,
    ModelUnavailable,
    ProviderError,
    QuotaExceeded,
    Usage,
)
from app.providers.openai_compat import OpenAIProvider, OpenRouterProvider

HELLO = [{"role": "user", "content": "Salut"}]


def with_transport(provider, handler):
    provider.transport = httpx2.MockTransport(handler)
    provider.max_retries = 0
    return provider


def sse(*events: str) -> httpx2.Response:
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content="".join(events).encode()
    )


async def collect(stream) -> str:
    return "".join([chunk async for chunk in stream if isinstance(chunk, str)])


async def usage_of(stream) -> Usage | None:
    return next((chunk for chunk in [c async for c in stream] if isinstance(chunk, Usage)), None)


# --- OpenRouter : catalogue et validation de clé -------------------------------------

CATALOG = {
    "data": [
        {
            "id": "acme/petit:free",
            "name": "Acme: Petit (free)",
            "context_length": 32000,
            "architecture": {"output_modalities": ["text"]},
            "pricing": {"prompt": "0", "completion": "0"},
            "top_provider": {"max_completion_tokens": 4000},
        },
        {
            "id": "acme/grand",
            "name": "Acme: Grand",
            "context_length": 200000,
            "architecture": {"output_modalities": ["text"]},
            "pricing": {"prompt": "0.000004", "completion": "0.00002"},
        },
        {
            "id": "acme/peintre",
            "name": "Acme: Peintre",
            "architecture": {"output_modalities": ["image"]},
            "pricing": {"prompt": "0", "completion": "0"},
        },
    ]
}


@respx.mock
async def test_openrouter_catalog_needs_no_key_and_marks_free_models():
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=CATALOG)
    )
    models = await OpenRouterProvider().list_models(None)

    assert "authorization" not in route.calls.last.request.headers
    assert [m.id for m in models] == ["acme/petit:free", "acme/grand"]
    assert models[0].free and not models[1].free
    assert models[1].input_price == 4.0
    assert models[1].output_price == 20.0
    assert models[0].max_output_tokens == 4000


@respx.mock
async def test_openrouter_catalog_sends_the_service_key_when_configured():
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=CATALOG)
    )
    await OpenRouterProvider().list_models("sk-or-service")
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-or-service"


@respx.mock
async def test_openrouter_validate_key():
    respx.get("https://openrouter.ai/api/v1/key").mock(
        side_effect=lambda request: httpx.Response(
            200 if request.headers["authorization"] == "Bearer sk-or-bonne" else 401, json={}
        )
    )
    await OpenRouterProvider().validate_key("sk-or-bonne")
    with pytest.raises(InvalidKey):
        await OpenRouterProvider().validate_key("sk-or-mauvaise")


# --- Protocole « chat completions » (OpenRouter et OpenAI) ---------------------------


def openai_chunk(text: str) -> str:
    payload = {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def test_openrouter_stream_uses_the_user_key_and_yields_text():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return sse(openai_chunk("Bon"), openai_chunk("jour"), "data: [DONE]\n\n")

    provider = with_transport(OpenRouterProvider(), handler)
    text = await collect(
        provider.stream_chat("sk-or-user", ModelInfo(id="acme/petit:free", name="Petit"), HELLO)
    )

    assert text == "Bonjour"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-or-user"
    assert seen["body"]["model"] == "acme/petit:free"
    assert seen["body"]["stream"] is True
    assert seen["body"]["messages"] == HELLO


@pytest.mark.parametrize(
    ("status", "code", "expected"),
    [
        (401, None, InvalidKey),
        (402, None, InsufficientCredit),
        (404, None, ModelUnavailable),
        (429, None, QuotaExceeded),
        (429, "insufficient_quota", InsufficientCredit),
        (500, None, ProviderError),
    ],
)
async def test_openai_errors_are_translated(status, code, expected):
    def handler(_request):
        return httpx2.Response(status, json={"error": {"message": "non", "code": code}})

    provider = with_transport(OpenAIProvider(), handler)
    with pytest.raises(expected) as raised:
        await collect(provider.stream_chat("sk-x", ModelInfo(id="gpt-test", name="gpt"), HELLO))
    assert type(raised.value) is expected


async def test_openai_lists_only_chat_models_newest_first():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/models"
        ids = ["o3", "gpt-5", "text-embedding-3-small", "gpt-4o-audio-preview", "dall-e-3"]
        data = [
            {"id": model_id, "object": "model", "created": index, "owned_by": "openai"}
            for index, model_id in enumerate(ids)
        ]
        return httpx2.Response(200, json={"object": "list", "data": data})

    provider = with_transport(OpenAIProvider(), handler)
    assert [m.id for m in await provider.list_models("sk-x")] == ["gpt-5", "o3"]


# --- Anthropic -----------------------------------------------------------------------


def anthropic_event(name: str, payload: dict) -> str:
    return f"event: {name}\ndata: {json.dumps({'type': name, **payload})}\n\n"


def anthropic_stream(*texts: str, stop_reason: str = "end_turn") -> httpx2.Response:
    message = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    events = [
        anthropic_event("message_start", {"message": message}),
        anthropic_event(
            "content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}}
        ),
        *[
            anthropic_event(
                "content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": text}}
            )
            for text in texts
        ],
        anthropic_event("content_block_stop", {"index": 0}),
        anthropic_event(
            "message_delta",
            {
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 2},
            },
        ),
        anthropic_event("message_stop", {}),
    ]
    return sse(*events)


async def test_anthropic_stream_separates_system_prompt_and_caps_max_tokens():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers["x-api-key"]
        seen["body"] = json.loads(request.content)
        return anthropic_stream("Bon", "jour")

    provider = with_transport(AnthropicProvider(), handler)
    model = ModelInfo(id="claude-test", name="Claude Test", max_output_tokens=128000)
    messages = [{"role": "system", "content": "Sois bref."}, *HELLO]
    text = await collect(provider.stream_chat("sk-ant-user", model, messages))

    assert text == "Bonjour"
    assert seen["path"] == "/v1/messages"
    assert seen["key"] == "sk-ant-user"
    assert seen["body"]["system"] == "Sois bref."
    assert seen["body"]["messages"] == HELLO
    assert seen["body"]["max_tokens"] == 64000
    assert seen["body"]["stream"] is True


async def test_anthropic_max_tokens_follows_a_smaller_model_limit():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return anthropic_stream("ok")

    provider = with_transport(AnthropicProvider(), handler)
    model = ModelInfo(id="claude-test", name="Claude Test", max_output_tokens=8192)
    await collect(provider.stream_chat("sk-ant-user", model, HELLO))

    assert seen["body"]["max_tokens"] == 8192
    assert "system" not in seen["body"]


async def test_anthropic_refusal_is_reported_after_the_text():
    provider = with_transport(
        AnthropicProvider(), lambda _request: anthropic_stream("Je", stop_reason="refusal")
    )
    chunks = []
    with pytest.raises(ProviderError, match="refusé"):
        async for chunk in provider.stream_chat(
            "sk-ant-user", ModelInfo(id="claude-test", name="Claude"), HELLO
        ):
            chunks.append(chunk)
    assert chunks == ["Je", Usage(input_tokens=1, output_tokens=2)]


@pytest.mark.parametrize(
    ("status", "error_type", "message", "expected"),
    [
        (401, "authentication_error", "invalid x-api-key", InvalidKey),
        (404, "not_found_error", "model: nope", ModelUnavailable),
        (429, "rate_limit_error", "slow down", QuotaExceeded),
        (400, "invalid_request_error", "Your credit balance is too low", InsufficientCredit),
        (400, "invalid_request_error", "messages: bad", ProviderError),
        (529, "overloaded_error", "Overloaded", ProviderError),
    ],
)
async def test_anthropic_errors_are_translated(status, error_type, message, expected):
    def handler(_request):
        body = {"type": "error", "error": {"type": error_type, "message": message}}
        return httpx2.Response(status, json=body)

    provider = with_transport(AnthropicProvider(), handler)
    with pytest.raises(expected) as raised:
        await collect(
            provider.stream_chat("sk-ant-x", ModelInfo(id="claude-test", name="Claude"), HELLO)
        )
    assert type(raised.value) is expected


async def test_anthropic_lists_models_with_their_limits():
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["x-api-key"] == "sk-ant-user"
        model = {
            "type": "model",
            "id": "claude-opus-5-5",
            "display_name": "Claude Opus 5.5",
            "created_at": "2026-01-01T00:00:00Z",
            "max_input_tokens": 1000000,
            "max_tokens": 128000,
        }
        body = {"data": [model], "has_more": False, "first_id": model["id"], "last_id": model["id"]}
        return httpx2.Response(200, json=body)

    provider = with_transport(AnthropicProvider(), handler)
    await provider.validate_key("sk-ant-user")
    assert await provider.list_models("sk-ant-user") == [
        ModelInfo(
            id="claude-opus-5-5",
            name="Claude Opus 5.5",
            accepts_images=True,
            context_length=1000000,
            max_output_tokens=128000,
        )
    ]
