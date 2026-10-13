from tests.conftest import add_key
from tests.test_chat import parse_sse, send, stored_messages


def start_conversation(client, content="Salut") -> str:
    return parse_sse(send(client, content).text)[0][1]["conversation"]["id"]


def test_conversations_are_listed_most_recent_first(client, providers, user):
    add_key(client)
    first = start_conversation(client, "Première")
    second = start_conversation(client, "Seconde")
    assert [c["id"] for c in client.get("/api/conversations").json()] == [second, first]

    send(client, "Encore", conversation_id=first)
    assert [c["id"] for c in client.get("/api/conversations").json()] == [first, second]


def test_rename_and_delete(client, providers, user):
    add_key(client)
    conversation_id = start_conversation(client)

    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": " Projet "})
    assert renamed.json()["title"] == "Projet"

    assert client.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert client.get("/api/conversations").json() == []
    assert client.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert stored_messages() == []


def test_long_first_message_gives_a_short_title(client, providers, user):
    add_key(client)
    send(client, "mot " * 100)
    assert len(client.get("/api/conversations").json()[0]["title"]) <= 60


def test_conversations_are_private_to_each_user(client, providers, user, other_client):
    add_key(client)
    add_key(other_client)
    conversation_id = start_conversation(client, "Secret d'Alice")
    url = f"/api/conversations/{conversation_id}"

    assert other_client.get("/api/conversations").json() == []
    assert other_client.get(url).status_code == 404
    assert other_client.patch(url, json={"title": "Volé"}).status_code == 404
    assert other_client.delete(url).status_code == 404
    assert other_client.post(f"{url}/regenerate", json={}).status_code == 404
    assert send(other_client, "Intrusion", conversation_id=conversation_id).status_code == 404

    assert client.get(url).json()["title"] == "Secret d'Alice"
    assert stored_messages() == [("user", "Secret d'Alice"), ("assistant", "Bonjour !")]
