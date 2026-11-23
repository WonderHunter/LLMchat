from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    # Incrémenté au changement de mot de passe : les sessions ouvertes avant ne valent plus.
    token_version: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    created_at: datetime = Field(default_factory=utcnow)


class ProviderKey(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    provider: str
    key_enc: str
    last4: str
    # Ne concerne qu'OpenRouter : limite l'utilisateur aux modèles ":free".
    free_only: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class Conversation(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    title: str
    provider: str
    model: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(foreign_key="conversation.id", index=True, ondelete="CASCADE")
    role: str
    content: str
    provider: str | None = None
    model: str | None = None
    # Consommation des réponses ; vide pour les questions et quand le fournisseur ne dit rien.
    input_tokens: int | None = None
    output_tokens: int | None = None
    # En dollars. Vide si ni le fournisseur ni son catalogue ne donnent de prix.
    cost: float | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Attachment(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    # Vide tant que le fichier est envoyé mais pas encore joint à un message.
    message_id: int | None = Field(
        default=None, foreign_key="message.id", index=True, ondelete="CASCADE"
    )
    kind: str  # "image" ou "text"
    filename: str
    media_type: str
    size: int
    # Les images sont gardées telles quelles ; des documents, on ne garde que le texte.
    data: bytes | None = Field(default=None, sa_type=LargeBinary)
    text: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
