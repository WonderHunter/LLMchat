from tests.conftest import add_key
from tests.test_chat import parse_sse, send, stored_messages


def start(client, *questions: str) -> tuple[str, list[dict]]:
    """Mène une conversation et renvoie son identifiant et ses messages."""
    conversation_id = parse_sse(send(client, questions[0]).text)[0][1]["conversation"]["id"]
    for question in questions[1:]:
        send(client, question, conversation_id=conversation_id)
    messages = client.get(f"/api/conversations/{conversation_id}").json()["messages"]
    return conversation_id, messages


def edit(client, conversation_id: str, message_id: int, content: str, **extra):
    return client.post(
        f"/api/conversations/{conversation_id}/messages/{message_id}/edit",
        json={"content": content, **extra},
    )


def test_editing_a_question_rewrites_it_and_drops_what_followed(client, providers, user):
    add_key(client)
    conversation_id, messages = start(client, "Un", "Deux", "Trois")
    providers["openrouter"].chunks = ["Nouvelle", " suite"]

    response = edit(client, conversation_id, messages[2]["id"], "Deux, corrigé")

    events = parse_sse(response.text)
    assert events[0][1]["edited_message"]["content"] == "Deux, corrigé"
    assert events[0][1]["edited_message"]["id"] == messages[2]["id"]
    assert events[-1][1]["message"]["content"] == "Nouvelle suite"
    assert stored_messages() == [
        ("user", "Un"),
        ("assistant", "Bonjour !"),
        ("user", "Deux, corrigé"),
        ("assistant", "Nouvelle suite"),
    ]
    assert providers["openrouter"].chat_calls[-1]["messages"] == [
        {"role": "user", "content": "Un"},
        {"role": "assistant", "content": "Bonjour !"},
        {"role": "user", "content": "Deux, corrigé"},
    ]


def test_editing_the_last_question_only_replaces_its_reply(client, providers, user):
    add_key(client)
    conversation_id, messages = start(client, "Un", "Deux")
    edit(client, conversation_id, messages[2]["id"], "Deux bis")
    assert [content for _, content in stored_messages()] == [
        "Un",
        "Bonjour !",
        "Deux bis",
        "Bonjour !",
    ]


def test_edit_can_switch_model(client, providers, user):
    add_key(client)
    add_key(client, "openai")
    conversation_id, messages = start(client, "Un")
    edit(client, conversation_id, messages[0]["id"], "Un bis", provider="openai", model="gpt-test")
    assert len(providers["openai"].chat_calls) == 1
    assert client.get(f"/api/conversations/{conversation_id}").json()["model"] == "gpt-test"


def test_only_questions_of_that_conversation_can_be_edited(client, providers, user):
    add_key(client)
    conversation_id, messages = start(client, "Un")
    other_id, other_messages = start(client, "Ailleurs")

    assert edit(client, conversation_id, messages[1]["id"], "Réponse trafiquée").status_code == 400
    assert edit(client, conversation_id, other_messages[0]["id"], "Mélange").status_code == 404
    assert edit(client, conversation_id, 99999, "Inconnu").status_code == 404
    assert edit(client, conversation_id, messages[0]["id"], "").status_code == 422
    assert [content for _, content in stored_messages()] == [
        "Un",
        "Bonjour !",
        "Ailleurs",
        "Bonjour !",
    ]


def test_refused_edit_changes_nothing(client, providers, user):
    add_key(client)
    conversation_id, messages = start(client, "Un", "Deux")
    # Modèle payant alors que seuls les gratuits sont autorisés : refus avant toute écriture.
    response = edit(client, conversation_id, messages[0]["id"], "Un bis", model="acme/grand")
    assert response.status_code == 403
    assert len(stored_messages()) == 4
    assert stored_messages()[0] == ("user", "Un")


def test_nobody_else_can_edit_my_messages(client, providers, user, other_client):
    add_key(client)
    add_key(other_client)
    conversation_id, messages = start(client, "Privé")
    assert edit(other_client, conversation_id, messages[0]["id"], "Piraté").status_code == 404
    assert stored_messages()[0] == ("user", "Privé")
