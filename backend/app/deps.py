from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models import User
from app.security import SESSION_COOKIE, read_session_token

SessionDep = Annotated[Session, Depends(get_session)]


def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    user_id = read_session_token(token) if token else None
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non authentifié")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
