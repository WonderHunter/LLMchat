from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def _as_utc(value: datetime) -> str:
    # SQLite rend des dates sans fuseau : on précise UTC pour que le navigateur convertisse bien.
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc, return_type=str)]


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: str | None
    model: str | None
    created_at: UtcDatetime


class ConversationOut(BaseModel):
    id: str
    title: str
    provider: str
    model: str
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]
