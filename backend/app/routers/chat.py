import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import engine
from app.deps import CurrentUser, SessionDep
from app.models import Conversation, Message, User, utcnow
from app.providers.base import ChatMessage, ModelInfo, Provider, ProviderError
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
    content: str = Field(min_length=1, max_length=400_000)


class RegenerateIn(BaseModel):
    provider: str | None = None
    model: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _dump(schema: type[BaseModel], row) -> dict:
    return schema(**row.model_dump()).model_dump(mode="json")


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


def _save_reply(conversation_id: str, provider_id: str, model_id: str, text: str) -> dict | None:
    if not text:
        return None
    # Session propre au flux : celle de la requête peut être fermée quand on arrive ici.
    with Session(engine) as session:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=text,
            provider=provider_id,
            model=model_id,
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
    error: ProviderError | None = None
    saved = None
    try:
        async for chunk in provider.stream_chat(key, model, history):
            parts.append(chunk)
            yield _sse("delta", {"text": chunk})
    except ProviderError as exc:
        error = exc
    except Exception:
        logger.exception("Erreur inattendue pendant la génération")
        error = ProviderError("Une erreur interne est survenue pendant la génération.")
    finally:
        # Exécuté aussi quand le client coupe la connexion : la réponse partielle est gardée.
        saved = _save_reply(conversation_id, provider.id, model.id, "".join(parts))
    if error is not None:
        yield _sse("error", {"code": error.code, "message": error.message})
    yield _sse("done", {"message": saved})


def _streaming_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _history(messages: list[Message]) -> list[ChatMessage]:
    return [{"role": m.role, "content": m.content} for m in messages]


@router.post("/chat")
async def chat(body: ChatIn, user: CurrentUser, session: SessionDep) -> StreamingResponse:
    provider, key, model = await _resolve(session, user, body.provider, body.model)

    if body.conversation_id:
        conversation = get_owned_conversation(session, user.id, body.conversation_id)
        conversation.provider, conversation.model = provider.id, model.id
    else:
        title = " ".join(body.content.split())[:_TITLE_LENGTH] or "Nouvelle conversation"
        conversation = Conversation(
            user_id=user.id, title=title, provider=provider.id, model=model.id
        )
    conversation.updated_at = utcnow()
    session.add(conversation)
    session.flush()

    user_message = Message(conversation_id=conversation.id, role="user", content=body.content)
    session.add(user_message)
    session.commit()
    session.refresh(conversation)
    session.refresh(user_message)

    start = {
        "conversation": _dump(ConversationOut, conversation),
        "user_message": _dump(MessageOut, user_message),
    }
    history = _history(get_messages(session, conversation.id))
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
        stream_reply(conversation_id, provider, key, model, _history(messages), start)
    )
