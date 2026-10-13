import base64
import json
from datetime import timedelta

import httpx
import httpx2
import pytest
import respx
from sqlmodel import Session, select

from app.attachments import MAX_IMAGE_BYTES, MAX_TEXT_CHARS, PENDING_HOURS
from app.db import engine
from app.models import Attachment, utcnow
from app.providers.anthropic import AnthropicProvider
from app.providers.base import ImagePart, ModelInfo
from app.providers.openai_compat import OpenAIProvider, OpenRouterProvider
from tests.conftest import PASSWORD, add_key
from tests.test_chat import parse_sse, send
from tests.test_providers import anthropic_stream, collect, openai_chunk, sse, with_transport

# Le plus petit PNG valide : un pixel transparent.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def make_pdf(text: str) -> bytes:
    """Un PDF d'une page contenant ce texte, avec une table de références correcte."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return pdf


def upload(client, name: str, data: bytes, media_type: str = "application/octet-stream"):
    return client.post("/api/attachments", files={"file": (name, data, media_type)})


def uploaded(client, name: str, data: bytes) -> dict:
    response = upload(client, name, data)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def vision(providers):
    """Rend le modèle gratuit de test capable de lire les images."""
    model = ModelInfo(id="acme/petit:free", name="Petit (free)", free=True, accepts_images=True)
    providers["openrouter"].models[0] = model
    return providers


# --- Envoi d'un fichier ---------------------------------------------------------------


def test_upload_requires_authentication(client):
    assert upload(client, "a.png", PNG).status_code == 401


def test_image_is_recognised_by_its_content_not_its_name(client, user):
    attachment = uploaded(client, "photo.txt", PNG)
    assert attachment["kind"] == "image"
    assert attachment["media_type"] == "image/png"
    assert attachment["size"] == len(PNG)

    served = client.get(f"/api/attachments/{attachment['id']}")
    assert served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert "sandbox" in served.headers["content-security-policy"]


def test_text_file_keeps_only_its_text(client, user):
    attachment = uploaded(client, "notes.md", "# Titre\n\nÉté à Noël.\n".encode())
    assert attachment["kind"] == "text"
    with Session(engine) as session:
        row = session.get(Attachment, attachment["id"])
    assert row.text == "# Titre\n\nÉté à Noël."
    assert row.data is None


def test_pdf_text_is_extracted(client, user):
    attachment = uploaded(client, "rapport.pdf", make_pdf("Bonjour depuis le PDF"))
    assert (attachment["kind"], attachment["media_type"]) == ("text", "application/pdf")
    with Session(engine) as session:
        assert "Bonjour depuis le PDF" in session.get(Attachment, attachment["id"]).text


@pytest.mark.parametrize(
    ("name", "data", "status", "message"),
    [
        ("archive.zip", b"PK\x03\x04\x00\xff\xfe\x00binaire", 415, "non pris en charge"),
        ("vide.txt", b"   \n", 422, "vide"),
        ("scan.pdf", make_pdf(""), 422, "texte lisible"),
        ("casse.pdf", b"%PDF-1.4 pas vraiment un pdf", 422, "illisible"),
        ("roman.txt", b"a" * (MAX_TEXT_CHARS + 1), 413, "trop long"),
        ("enorme.png", PNG + b"\x00" * MAX_IMAGE_BYTES, 413, "trop lourde"),
    ],
    # Sans ces noms, pytest mettrait le contenu des fichiers dans l'identifiant du test.
    ids=["zip", "vide", "pdf-scanne", "pdf-abime", "texte-trop-long", "image-trop-lourde"],
)
def test_unusable_files_are_refused_with_a_reason(client, user, name, data, status, message):
    response = upload(client, name, data)
    assert response.status_code == status
    assert message in response.json()["detail"]
    with Session(engine) as session:
        assert session.exec(select(Attachment)).first() is None


def test_filename_cannot_carry_a_path(client, user):
    assert uploaded(client, "../../etc/passwd.txt", b"contenu")["filename"] == "passwd.txt"


def test_pending_file_can_be_discarded(client, user):
    attachment = uploaded(client, "a.png", PNG)
    assert client.delete(f"/api/attachments/{attachment['id']}").status_code == 204
    assert client.get(f"/api/attachments/{attachment['id']}").status_code == 404


def test_files_never_sent_are_purged_at_the_next_upload(client, user):
    old = uploaded(client, "oublie.png", PNG)
    with Session(engine) as session:
        row = session.get(Attachment, old["id"])
        row.created_at = utcnow() - timedelta(hours=PENDING_HOURS + 1)
        session.add(row)
        session.commit()

    recent = uploaded(client, "recent.png", PNG)
    with Session(engine) as session:
        assert [a.id for a in session.exec(select(Attachment))] == [recent["id"]]


# --- Dans une conversation ------------------------------------------------------------


def test_message_with_image_and_document_reaches_the_model(client, vision, user):
    add_key(client)
    image = uploaded(client, "schema.png", PNG)
    notes = uploaded(client, "notes.txt", b"Le budget est de 12 euros.")

    response = send(client, "Résume.", attachment_ids=[image["id"], notes["id"]])
    assert response.status_code == 200

    start = parse_sse(response.text)[0][1]
    assert [a["filename"] for a in start["user_message"]["attachments"]] == [
        "schema.png",
        "notes.txt",
    ]
    sent = vision["openrouter"].chat_calls[-1]["messages"][-1]
    assert sent["images"] == [ImagePart("image/png", PNG)]
    assert sent["content"] == (
        '<fichier nom="notes.txt">\nLe budget est de 12 euros.\n</fichier>\n\nRésume.'
    )

    detail = client.get(f"/api/conversations/{start['conversation']['id']}").json()
    assert [a["kind"] for a in detail["messages"][0]["attachments"]] == ["image", "text"]
    assert detail["messages"][1]["attachments"] == []


def test_image_alone_is_a_valid_message_and_names_the_conversation(client, vision, user):
    add_key(client)
    other = uploaded(client, "autre.png", PNG)
    image = uploaded(client, "chat.png", PNG)
    # Le titre vient du premier fichier joint, dans l'ordre choisi par l'utilisateur.
    response = send(client, "", attachment_ids=[image["id"], other["id"]])
    assert response.status_code == 200
    assert parse_sse(response.text)[0][1]["conversation"]["title"] == "chat.png"
    assert send(client, "   ").status_code == 422


def test_model_that_cannot_read_images_refuses_them_before_anything_is_saved(
    client, providers, user
):
    add_key(client)
    image = uploaded(client, "schema.png", PNG)
    response = send(client, "Regarde", attachment_ids=[image["id"]])
    assert response.status_code == 400
    assert "ne lit pas les images" in response.json()["detail"]
    assert client.get("/api/conversations").json() == []
    # Le fichier reste disponible pour un autre modèle.
    with Session(engine) as session:
        assert session.get(Attachment, image["id"]).message_id is None


def test_documents_work_with_models_that_cannot_read_images(client, providers, user):
    add_key(client)
    notes = uploaded(client, "notes.txt", b"Texte simple")
    assert send(client, "Lis", attachment_ids=[notes["id"]]).status_code == 200
    assert "Texte simple" in providers["openrouter"].chat_calls[-1]["messages"][-1]["content"]


def test_earlier_images_are_replaced_by_a_note_when_the_model_changes(client, vision, user):
    add_key(client)
    add_key(client, "openai")  # gpt-test : pas d'images dans les modèles de test
    image = uploaded(client, "schema.png", PNG)
    conversation_id = parse_sse(send(client, "Regarde", attachment_ids=[image["id"]]).text)[0][1][
        "conversation"
    ]["id"]

    send(client, "Et alors ?", provider="openai", model="gpt-test", conversation_id=conversation_id)

    first = vision["openai"].chat_calls[-1]["messages"][0]
    assert "images" not in first
    assert first["content"] == (
        "[Image « schema.png » non transmise : ce modèle ne lit pas les images.]\n\nRegarde"
    )


def test_a_file_can_be_sent_only_once_and_only_by_its_owner(client, vision, user, other_client):
    add_key(client)
    add_key(other_client)
    image = uploaded(client, "a.png", PNG)

    assert other_client.get(f"/api/attachments/{image['id']}").status_code == 404
    assert other_client.delete(f"/api/attachments/{image['id']}").status_code == 404
    assert send(other_client, "Vol", attachment_ids=[image["id"]]).status_code == 400

    assert send(client, "Un", attachment_ids=[image["id"]]).status_code == 200
    assert send(client, "Deux", attachment_ids=[image["id"]]).status_code == 400
    assert client.delete(f"/api/attachments/{image['id']}").status_code == 409


def test_attachments_survive_an_edit_and_a_regeneration(client, vision, user):
    add_key(client)
    image = uploaded(client, "a.png", PNG)
    start = parse_sse(send(client, "Un", attachment_ids=[image["id"]]).text)[0][1]
    conversation_id, message_id = start["conversation"]["id"], start["user_message"]["id"]

    client.post(f"/api/conversations/{conversation_id}/regenerate", json={})
    assert vision["openrouter"].chat_calls[-1]["messages"][0]["images"] == [
        ImagePart("image/png", PNG)
    ]

    edited = client.post(
        f"/api/conversations/{conversation_id}/messages/{message_id}/edit",
        json={"content": "Un bis"},
    )
    assert parse_sse(edited.text)[0][1]["edited_message"]["attachments"][0]["id"] == image["id"]
    assert vision["openrouter"].chat_calls[-1]["messages"][0]["images"]


def test_attachments_disappear_with_their_conversation_and_account(client, vision, user):
    add_key(client)
    first = uploaded(client, "a.png", PNG)
    second = uploaded(client, "b.png", PNG)
    pending = uploaded(client, "c.png", PNG)
    conversation_id = parse_sse(send(client, "Un", attachment_ids=[first["id"]]).text)[0][1][
        "conversation"
    ]["id"]
    send(client, "Deux", attachment_ids=[second["id"]])

    client.delete(f"/api/conversations/{conversation_id}")
    with Session(engine) as session:
        assert {a.id for a in session.exec(select(Attachment))} == {second["id"], pending["id"]}

    client.post("/api/auth/delete-account", json={"password": PASSWORD})
    with Session(engine) as session:
        assert session.exec(select(Attachment)).first() is None


def test_models_say_whether_they_read_images(client, vision, user):
    add_key(client)
    client.patch("/api/keys/openrouter", json={"free_only": False})
    models = client.get("/api/models").json()[0]["models"]
    assert [(m["id"], m["accepts_images"]) for m in models] == [
        ("acme/petit:free", True),
        ("acme/grand", False),
    ]


# --- Format envoyé à chaque fournisseur ------------------------------------------------

WITH_IMAGE = [{"role": "user", "content": "Décris", "images": [ImagePart("image/png", PNG)]}]
ENCODED = base64.b64encode(PNG).decode()


async def test_openai_format_sends_images_as_data_urls():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return sse(openai_chunk("ok"), "data: [DONE]\n\n")

    provider = with_transport(OpenRouterProvider(), handler)
    await collect(provider.stream_chat("sk", ModelInfo(id="a/b", name="b"), WITH_IMAGE))

    assert seen["body"]["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Décris"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ENCODED}"}},
            ],
        }
    ]


async def test_anthropic_format_puts_images_before_the_text():
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return anthropic_stream("ok")

    provider = with_transport(AnthropicProvider(), handler)
    await collect(provider.stream_chat("sk", ModelInfo(id="claude-test", name="c"), WITH_IMAGE))

    assert seen["body"]["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": ENCODED},
                },
                {"type": "text", "text": "Décris"},
            ],
        }
    ]


@respx.mock
async def test_openrouter_catalog_tells_which_models_read_images():
    catalog = {
        "data": [
            {"id": "a/voit", "architecture": {"input_modalities": ["text", "image"]}},
            {"id": "a/aveugle", "architecture": {"input_modalities": ["text"]}},
            {"id": "a/inconnu"},
        ]
    }
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, json=catalog)
    )
    models = await OpenRouterProvider().list_models(None)
    assert [m.accepts_images for m in models] == [True, False, False]


async def test_anthropic_reads_the_image_capability_of_each_model():
    def model(model_id: str, capabilities: dict | None) -> dict:
        return {
            "type": "model",
            "id": model_id,
            "display_name": model_id,
            "created_at": "2026-01-01T00:00:00Z",
            "max_input_tokens": 1000,
            "max_tokens": 100,
            "capabilities": capabilities,
        }

    def capabilities(images: bool) -> dict:
        flag = {"supported": False}
        return {
            "batch": flag,
            "citations": flag,
            "code_execution": flag,
            "context_management": None,
            "effort": {
                **flag,
                "low": flag,
                "medium": flag,
                "high": flag,
                "xhigh": flag,
                "max": flag,
            },
            "image_input": {"supported": images},
            "pdf_input": flag,
            "structured_outputs": flag,
            "thinking": {**flag, "types": {"adaptive": flag, "enabled": flag}},
        }

    def handler(_request: httpx2.Request) -> httpx2.Response:
        data = [
            model("voit", capabilities(True)),
            model("aveugle", capabilities(False)),
            model("inconnu", None),
        ]
        return httpx2.Response(
            200, json={"data": data, "has_more": False, "first_id": "voit", "last_id": "inconnu"}
        )

    provider = with_transport(AnthropicProvider(), handler)
    models = await provider.list_models("sk-ant")
    assert [(m.id, m.accepts_images) for m in models] == [
        ("voit", True),
        ("aveugle", False),
        ("inconnu", True),
    ]


async def test_openai_guesses_image_support_from_the_model_name():
    def handler(_request: httpx2.Request) -> httpx2.Response:
        data = [
            {"id": model_id, "object": "model", "created": index, "owned_by": "openai"}
            for index, model_id in enumerate(["gpt-3.5-turbo", "o3-mini", "gpt-5"])
        ]
        return httpx2.Response(200, json={"object": "list", "data": data})

    provider = with_transport(OpenAIProvider(), handler)
    models = await provider.list_models("sk")
    assert {m.id: m.accepts_images for m in models} == {
        "gpt-5": True,
        "o3-mini": False,
        "gpt-3.5-turbo": False,
    }
