from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import select

from app.config import get_settings
from app.deps import CurrentUser, SessionDep
from app.models import User
from app.ratelimit import (
    login_failures_by_email,
    login_failures_by_ip,
    registrations_by_ip,
    too_many,
)
from app.security import SESSION_COOKIE, create_session_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginCredentials(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    id: int
    email: str


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


def _set_session_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user_id),
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.get("/config")
def auth_config() -> dict[str, bool]:
    settings = get_settings()
    return {"allow_registration": settings.allow_registration, "demo": settings.demo_mode}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, request: Request, response: Response, session: SessionDep) -> User:
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Les inscriptions sont fermées")
    ip = _client_ip(request)
    if (wait := registrations_by_ip.retry_after(ip)) is not None:
        raise too_many(wait)
    email = body.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail")
    user = User(email=email, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    registrations_by_ip.record(ip)
    _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginCredentials, request: Request, response: Response, session: SessionDep
) -> User:
    ip, email = _client_ip(request), body.email.lower()
    waits = (login_failures_by_ip.retry_after(ip), login_failures_by_email.retry_after(email))
    if any(wait is not None for wait in waits):
        raise too_many(max(wait for wait in waits if wait is not None))

    user = session.exec(select(User).where(User.email == email)).first()
    if not verify_password(body.password, user.password_hash if user else None):
        login_failures_by_ip.record(ip)
        login_failures_by_email.record(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou mot de passe incorrect")
    login_failures_by_email.forget(email)
    _set_session_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
