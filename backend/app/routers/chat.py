import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, col, select

from app.attachments import MAX_PER_MESSAGE, attachments_of, describe
from app.db import engine
from app.deps import CurrentUser, SessionDep
from app.models import Attachment, Conversation, Message, User, utcnow
from app.providers.base import (
    ChatMessage,
    ImagePart,
    ModelInfo,
    Provider,
    ProviderError,
    Usage,
)
from app.providers.registry import PROVIDERS
from app.routers.conversations import get_messages, get_owned_conversation
from app.routers.keys import get_key
from app.schemas import ConversationOut, MessageOut
from app.security import decrypt_secret
from app.services.catalog import catalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

_TITLE_LENGTH = 60


class ChatIn(BaseModel):
    conversation_id: str | None = None
    provider: str
    model: str
    content: str = Field(max_length=400_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=MAX_PER_MESSAGE)

    @model_validator(mode="after")
    def _not_empty(self) -> "ChatIn":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("Le message est vide")
        return self


class RegenerateIn(BaseModel):
    provider: str | None = None
    model: str | None = None


class EditIn(BaseModel):
    content: str = Field(min_length=1, max_length=400_000)
    provider: str | None = None
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _dump(schema: type[BaseModel], row) -> dict:
    return schema(**row.model_dump()).model_dump(mode="json")


def _dump_message(session: Session, message: Message) -> dict:
    """Un message avec la description de ses pièces jointes."""
    attachments = describe(session, [message.id]).get(message.id, [])
    return MessageOut(**message.model_dump(), attachments=attachments).model_dump(mode="json")


async def _resolve(
    session: Session, user: User, provider_id: str, model_id: str
) -> tuple[Provider, str, ModelInfo]:
    """Fournisseur, clé de l'utilisateur et modèle, après vérification des droits."""
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fournisseur inconnu")
    row = get_key(session, user.id, provider_id)
    if row is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Ajoutez d'abord une clé {provider.label} dans les réglages.",
        )
    key = decrypt_secret(row.key_enc)
    try:
        model = await catalog.find(user.id, provider_id, key, row.free_only, model_id)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    if model is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Ce modèle n'est pas autorisé avec vos réglages actuels."
        )
    return provider, key, model


def _cost(model: ModelInfo, usage: Usage) -> float | None:
    """Coût en dollars : celui annoncé par le fournisseur, sinon calculé d'après ses tarifs."""
    if usage.cost is not None:
        return usage.cost
    if model.free:
        return 0.0
    if model.input_price is None or model.output_price is None:
        return None
    total = usage.input_tokens * model.input_price + usage.output_tokens * model.output_price
    return total / 1_000_000


def _save_reply(
    conversation_id: str, provider_id: str, model: ModelInfo, text: str, usage: Usage | None
) -> dict | None:
    if not text:
        return None
    # Session propre au flux : celle de la requête peut être fermée quand on arrive ici.
    with Session(engine) as session:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            provider=provider_id,
            model=model.id,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cost=_cost(model, usage) if usage else None,
        )
        session.add(message)
        conversation = session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = utcnow()
            session.add(conversation)
        session.commit()
        session.refresh(message)
        return _dump(MessageOut, message)


async def stream_reply(
    conversation_id: str,
    provider: Provider,
    key: str,
    model: ModelInfo,
    history: list[ChatMessage],
    start: dict,
) -> AsyncIterator[str]:
    yield _sse("start", start)
    parts: list[str] = []
    usage: Usage | None = None
    error: ProviderError | None = None
    saved = None
    try:
        async for chunk in provider.stream_chat(key, model, history):
            if isinstance(chunk, Usage):
                usage = chunk
                continue
            parts.append(chunk)
            yield _sse("delta", {"text": chunk})
    except ProviderError as exc:
        error = exc
    except Exception:
        logger.exception("Erreur inattendue pendant la génération")
        error = ProviderError("Une erreur interne est survenue pendant la génération.")
    finally:
        # Exécuté aussi quand le client coupe la connexion : la réponse partielle est gardée.
        saved = _save_reply(conversation_id, provider.id, model, "".join(parts), usage)
    if error is not None:
        logger.warning("Génération interrompue chez %s (%s)", provider.id, error.code)
        yield _sse("error", {"code": error.code, "message": error.message})
    yield _sse("done", {"message": saved})


def _streaming_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _history(session: Session, messages: list[Message], model: ModelInfo) -> list[ChatMessage]:
    """La conversation telle qu'elle est envoyée au modèle, pièces jointes comprises."""
    attachments = attachments_of(session, [m.id for m in messages])
    history: list[ChatMessage] = []
    for message in messages:
        documents, notes, images = [], [], []
        for attachment in attachments.get(message.id, []):
            name = attachment.filename.replace('"', "'")
            if attachment.kind == "text":
                documents.append(f'<fichier nom="{name}">\n{attachment.text}\n</fichier>')
            elif model.accepts_images:
                images.append(ImagePart(attachment.media_type, attachment.data))
            else:
                # Une image d'un message précédent, alors que le modèle a changé depuis.
                notes.append(f"[Image « {name} » non transmise : ce modèle ne lit pas les images.]")
        content = "\n\n".join(part for part in (*documents, *notes, message.content) if part)
        entry: ChatMessage = {"role": message.role, "content": content}
        if images:
            entry["images"] = images
        history.append(entry)
    return history


def _claim_attachments(
    session: Session, user: User, attachment_ids: list[str], model: ModelInfo
) -> list[Attachment]:
    """Les fichiers en attente que l'utilisateur joint à son message, après vérifications."""
    if not attachment_ids:
        return []
    found = session.exec(
        select(Attachment).where(
            col(Attachment.id).in_(attachment_ids),
            Attachment.user_id == user.id,
            col(Attachment.message_id).is_(None),
        )
    ).all()
    if len(found) != len(set(attachment_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pièce jointe introuvable ou déjà envoyée")
    if not model.accepts_images and any(a.kind == "image" for a in found):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Ce modèle ne lit pas les images. Retirez-les ou choisissez un modèle qui les accepte.",
        )
    # Dans l'ordre où l'utilisateur les a joints, pas celui de la base.
    by_id = {attachment.id: attachment for attachment in found}
    return [by_id[attachment_id] for attachment_id in dict.fromkeys(attachment_ids)]


@router.post("/chat")
async def chat(body: ChatIn, user: CurrentUser, session: SessionDep) -> StreamingResponse:
    provider, key, model = await _resolve(session, user, body.provider, body.model)
    attachments = _claim_attachments(session, user, body.attachment_ids, model)

    if body.conversation_id:
        conversation = get_owned_conversation(session, user.id, body.conversation_id)
        conversation.provider, conversation.model = provider.id, model.id
    else:
        first_file = attachments[0].filename if attachments else "Nouvelle conversation"
        title = (" ".join(body.content.split()) or first_file)[:_TITLE_LENGTH]
        conversation = Conversation(
            user_id=user.id, title=title, provider=provider.id, model=model.id
        )
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.flush()

    user_message = Message(conversation_id=conversation.id, role="user", content=body.content)
    session.add(user_message)
    session.flush()
    for attachment in attachments:
        attachment.message_id = user_message.id
        session.add(attachment)
    session.commit()
    session.refresh(conversation)
    session.refresh(user_message)

    start = {
        "conversation": _dump(ConversationOut, conversation),
        "user_message": _dump_message(session, user_message),
    }
    history = _history(session, get_messages(session, conversation.id), model)
    return _streaming_response(stream_reply(conversation.id, provider, key, model, history, start))


@router.post("/conversations/{conversation_id}/regenerate")
async def regenerate(
    conversation_id: str, body: RegenerateIn, user: CurrentUser, session: SessionDep
) -> StreamingResponse:
    conversation = get_owned_conversation(session, user.id, conversation_id)
    provider, key, model = await _resolve(
        session, user, body.provider or conversation.provider, body.model or conversation.model
    )

    messages = get_messages(session, conversation_id)
    while messages and messages[-1].role == "assistant":
        session.delete(messages.pop())
    if not messages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Rien à régénérer")
    conversation.provider, conversation.model = provider.id, model.id
    session.add(conversation)
    session.commit()
    session.refresh(conversation)

    start = {"conversation": _dump(ConversationOut, conversation), "user_message": None}
    return _streaming_response(
        stream_reply(
            conversation_id, provider, key, model, _history(session, messages, model), start
        )
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/edit")
async def edit_message(
    conversation_id: str,
    message_id: int,
    body: EditIn,
    user: CurrentUser,
    session: SessionDep,
) -> StreamingResponse:
    """Réécrit une question, efface tout ce qui la suivait et génère une nouvelle réponse."""
    conversation = get_owned_conversation(session, user.id, conversation_id)
    messages = get_messages(session, conversation_id)
    edited = next((m for m in messages if m.id == message_id), None)
    if edited is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message introuvable")
    if edited.role != "user":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Seules vos questions sont modifiables")
    provider, key, model = await _resolve(
        session, user, body.provider or conversation.provider, body.model or conversation.model
    )

    kept = [m for m in messages if m.id <= message_id]
    for message in messages[len(kept) :]:
        session.delete(message)
    edited.content = body.content
    conversation.provider, conversation.model = provider.id, model.id
    conversation.updated_at = utcnow()
    session.add(edited)
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    session.refresh(edited)

    start = {
        "conversation": _dump(ConversationOut, conversation),
        "user_message": None,
        "edited_message": _dump_message(session, edited),
    }
    return _streaming_response(
        stream_reply(conversation_id, provider, key, model, _history(session, kept, model), start)
    )
