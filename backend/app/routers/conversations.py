from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, col, delete, select

from app.attachments import describe
from app.deps import CurrentUser, SessionDep
from app.models import Conversation, Message
from app.schemas import ConversationDetail, ConversationOut, MessageOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationPatch(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def get_owned_conversation(session: Session, user_id: int, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    # Même réponse qu'elle n'existe pas ou qu'elle appartienne à quelqu'un d'autre.
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation introuvable")
    return conversation


def get_messages(session: Session, conversation_id: str) -> list[Message]:
    return list(
        session.exec(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        ).all()
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(user: CurrentUser, session: SessionDep) -> list[Conversation]:
    return list(
        session.exec(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(col(Conversation.updated_at).desc())
        ).all()
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str, user: CurrentUser, session: SessionDep
) -> ConversationDetail:
    conversation = get_owned_conversation(session, user.id, conversation_id)
    rows = get_messages(session, conversation_id)
    attachments = describe(session, [m.id for m in rows])
    messages = [MessageOut(**m.model_dump(), attachments=attachments.get(m.id, [])) for m in rows]
    return ConversationDetail(**conversation.model_dump(), messages=messages)


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename_conversation(
    conversation_id: str, body: ConversationPatch, user: CurrentUser, session: SessionDep
) -> Conversation:
    conversation = get_owned_conversation(session, user.id, conversation_id)
    conversation.title = body.title.strip() or conversation.title
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: CurrentUser, session: SessionDep) -> None:
    conversation = get_owned_conversation(session, user.id, conversation_id)
    session.exec(delete(Message).where(col(Message.conversation_id) == conversation_id))
    session.delete(conversation)
    session.commit()
