import json

from sqlmodel import Session, select

from app.db import engine
from app.models import Message
from app.providers.base import QuotaExceeded
from app.routers.chat import stream_reply
from tests.conftest import add_key


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def send(client, content="Salut", provider="openrouter", model="acme/petit:free", **extra):
    return client.post(
        "/api/chat", json={"provider": provider, "model": model, "content": content, **extra}
    )


def stored_messages() -> list[tuple[str, str]]:
    with Session(engine) as session:
        return [(m.role, m.content) for m in session.exec(select(Message).order_by(Message.id))]


def test_chat_requires_authentication(client, providers):
    assert send(client).status_code == 401


def test_first_message_creates_the_conversation_and_streams_the_reply(client, providers, user):
    add_key(client)
    response = send(client, content="  Bonjour,\n comment vas-tu ?  ")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["start", "delta", "delta", "delta", "done"]

    start = events[0][1]
    assert start["conversation"]["title"] == "Bonjour, comment vas-tu ?"
    assert start["conversation"]["model"] == "acme/petit:free"
    assert "".join(data["text"] for name, data in events if name == "delta") == "Bonjour !"
    done = events[-1][1]["message"]
    assert done["role"] == "assistant"
    assert done["content"] == "Bonjour !"
    assert done["created_at"].endswith("+00:00")

    detail = client.get(f"/api/conversations/{start['conversation']['id']}").json()
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "  Bonjour,\n comment vas-tu ?  "),
        ("assistant", "Bonjour !"),
    ]


def test_the_user_key_and_full_history_are_sent_to_the_provider(client, providers, user):
    add_key(client)
    conversation_id = parse_sse(send(client, "Un").text)[0][1]["conversation"]["id"]
    send(client, "Deux", conversation_id=conversation_id)

    call = providers["openrouter"].chat_calls[-1]
    assert call["key"] == "sk-test-valide-1234"
    assert call["model"].id == "acme/petit:free"
    assert call["messages"] == [
        {"role": "user", "content": "Un"},
        {"role": "assistant", "content": "Bonjour !"},
        {"role": "user", "content": "Deux"},
    ]
    assert len(client.get("/api/conversations").json()) == 1


def test_chat_without_a_key_for_the_provider_is_refused(client, providers, user):
    add_key(client, "openai")
    response = send(client)
    assert response.status_code == 400
    assert "clé Openrouter" in response.json()["detail"]
    assert stored_messages() == []


def test_paid_openrouter_model_is_refused_while_free_only_is_on(client, providers, user):
    add_key(client)
    assert send(client, model="acme/grand").status_code == 403
    assert providers["openrouter"].chat_calls == []

    client.patch("/api/keys/openrouter", json={"free_only": False})
    assert send(client, model="acme/grand").status_code == 200
    assert providers["openrouter"].chat_calls[-1]["model"].id == "acme/grand"


def test_unknown_model_is_refused(client, providers, user):
    add_key(client, "anthropic")
    assert send(client, provider="anthropic", model="claude-inexistant").status_code == 403


def test_model_can_change_inside_a_conversation(client, providers, user):
    add_key(client)
    add_key(client, "anthropic")
    conversation_id = parse_sse(send(client).text)[0][1]["conversation"]["id"]
    send(
        client, "Suite", provider="anthropic", model="claude-test", conversation_id=conversation_id
    )

    detail = client.get(f"/api/conversations/{conversation_id}").json()
    assert (detail["provider"], detail["model"]) == ("anthropic", "claude-test")
    assert [m["model"] for m in detail["messages"] if m["role"] == "assistant"] == [
        "acme/petit:free",
        "claude-test",
    ]


def test_provider_error_before_any_text_keeps_the_question_only(client, providers, user):
    add_key(client)
    providers["openrouter"].chunks = []
    providers["openrouter"].chat_error = QuotaExceeded("OpenRouter")

    events = parse_sse(send(client).text)
    assert [name for name, _ in events] == ["start", "error", "done"]
    assert events[1][1]["code"] == "quota_exceeded"
    assert "Limite de requêtes" in events[1][1]["message"]
    assert events[2][1]["message"] is None
    assert stored_messages() == [("user", "Salut")]


def test_provider_error_mid_stream_keeps_the_partial_reply(client, providers, user):
    add_key(client)
    providers["openrouter"].chat_error = QuotaExceeded("OpenRouter")

    events = parse_sse(send(client).text)
    assert [name for name, _ in events] == ["start", "delta", "delta", "delta", "error", "done"]
    assert events[-1][1]["message"]["content"] == "Bonjour !"
    assert stored_messages() == [("user", "Salut"), ("assistant", "Bonjour !")]


def test_unexpected_error_does_not_leak_details(client, providers, user):
    add_key(client)
    providers["openrouter"].chat_error = RuntimeError("secret interne sk-xyz")

    response = send(client)
    assert "secret interne" not in response.text
    assert parse_sse(response.text)[-2][1]["code"] == "provider_error"


async def test_partial_reply_is_saved_when_the_client_disconnects(client, providers, user):
    add_key(client)
    conversation_id = parse_sse(send(client).text)[0][1]["conversation"]["id"]
    model = providers["openrouter"].models[0]

    stream = stream_reply(conversation_id, providers["openrouter"], "sk", model, [], {})
    await anext(stream)  # start
    await anext(stream)  # premier morceau
    await stream.aclose()  # le navigateur ferme la connexion

    assert stored_messages()[-1] == ("assistant", "Bon")


def test_regenerate_replaces_the_last_reply(client, providers, user):
    add_key(client)
    conversation_id = parse_sse(send(client).text)[0][1]["conversation"]["id"]
    providers["openrouter"].chunks = ["Nouvelle", " réponse"]

    response = client.post(f"/api/conversations/{conversation_id}/regenerate", json={})
    events = parse_sse(response.text)
    assert events[0][1]["user_message"] is None
    assert events[-1][1]["message"]["content"] == "Nouvelle réponse"
    assert stored_messages() == [("user", "Salut"), ("assistant", "Nouvelle réponse")]
    assert providers["openrouter"].chat_calls[-1]["messages"] == [
        {"role": "user", "content": "Salut"}
    ]


def test_regenerate_can_switch_model(client, providers, user):
    add_key(client)
    add_key(client, "openai")
    conversation_id = parse_sse(send(client).text)[0][1]["conversation"]["id"]

    client.post(
        f"/api/conversations/{conversation_id}/regenerate",
        json={"provider": "openai", "model": "gpt-test"},
    )
    assert len(providers["openai"].chat_calls) == 1
    assert client.get(f"/api/conversations/{conversation_id}").json()["model"] == "gpt-test"
