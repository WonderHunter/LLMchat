"""Décompte des tokens et coût des réponses."""

import json

import httpx2
import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import ModelInfo, Usage
from app.providers.openai_compat import OpenAIProvider, OpenRouterProvider
from tests.conftest import add_key
from tests.test_chat import parse_sse, send
from tests.test_providers import (
    HELLO,
    anthropic_stream,
    openai_chunk,
    sse,
    usage_of,
    with_transport,
)


def reply_of(response) -> dict:
    return parse_sse(response.text)[-1][1]["message"]


# --- Ce que l'application enregistre -------------------------------------------------


def test_free_model_costs_nothing(client, providers, user):
    add_key(client)
    reply = reply_of(send(client))
    assert (reply["input_tokens"], reply["output_tokens"]) == (12, 34)
    assert reply["cost"] == 0


def test_cost_is_computed_from_the_catalog_prices(client, providers, user):
    add_key(client)
    client.patch("/api/keys/openrouter", json={"free_only": False})
    # 12 tokens à 3 $ le million en entrée, 34 à 15 $ en sortie.
    assert reply_of(send(client, model="acme/grand"))["cost"] == pytest.approx(0.000546)


def test_cost_announced_by_the_provider_wins(client, providers, user):
    add_key(client)
    client.patch("/api/keys/openrouter", json={"free_only": False})
    providers["openrouter"].usage = Usage(input_tokens=12, output_tokens=34, cost=0.0123)
    assert reply_of(send(client, model="acme/grand"))["cost"] == 0.0123


def test_tokens_without_known_price_give_no_cost(client, providers, user):
    add_key(client, "openai")
    reply = reply_of(send(client, provider="openai", model="gpt-test"))
    assert reply["output_tokens"] == 34
    assert reply["cost"] is None


def test_reply_without_usage_is_still_saved(client, providers, user):
    add_key(client)
    providers["openrouter"].usage = None
    reply = reply_of(send(client))
    assert reply["content"] == "Bonjour !"
    assert reply["input_tokens"] is None and reply["cost"] is None


def test_usage_is_kept_with_the_conversation(client, providers, user):
    add_key(client)
    conversation_id = parse_sse(send(client).text)[0][1]["conversation"]["id"]
    question, answer = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
    assert question["output_tokens"] is None
    assert (answer["input_tokens"], answer["output_tokens"], answer["cost"]) == (12, 34, 0)


# --- Ce que renvoient les connecteurs ------------------------------------------------


def usage_chunk(**usage) -> str:
    payload = {
        "id": "c1",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "m",
        "choices": [],
        "usage": usage,
    }
    return f"data: {json.dumps(payload)}\n\n"


async def test_openai_asks_for_usage_and_reads_it():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return sse(
            openai_chunk("Salut"),
            usage_chunk(prompt_tokens=9, completion_tokens=4, total_tokens=13),
            "data: [DONE]\n\n",
        )

    provider = with_transport(OpenAIProvider(), handler)
    usage = await usage_of(provider.stream_chat("sk", ModelInfo(id="gpt", name="gpt"), HELLO))

    assert usage == Usage(input_tokens=9, output_tokens=4, cost=None)
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert "usage" not in seen["body"]


async def test_openrouter_asks_for_the_real_cost_and_reads_it():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return sse(
            openai_chunk("Salut"),
            usage_chunk(prompt_tokens=9, completion_tokens=4, total_tokens=13, cost=0.00021),
            "data: [DONE]\n\n",
        )

    provider = with_transport(OpenRouterProvider(), handler)
    usage = await usage_of(provider.stream_chat("sk", ModelInfo(id="a/b", name="b"), HELLO))

    assert usage == Usage(input_tokens=9, output_tokens=4, cost=0.00021)
    assert seen["body"]["usage"] == {"include": True}


async def test_stream_without_usage_chunk_yields_none():
    provider = with_transport(
        OpenAIProvider(), lambda _request: sse(openai_chunk("Salut"), "data: [DONE]\n\n")
    )
    assert (
        await usage_of(provider.stream_chat("sk", ModelInfo(id="gpt", name="gpt"), HELLO)) is None
    )


async def test_anthropic_reports_its_token_counts():
    provider = with_transport(AnthropicProvider(), lambda _request: anthropic_stream("Bon", "jour"))
    usage = await usage_of(
        provider.stream_chat("sk-ant", ModelInfo(id="claude-test", name="Claude"), HELLO)
    )
    assert usage == Usage(input_tokens=1, output_tokens=2, cost=None)
