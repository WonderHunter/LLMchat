from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from app.config import get_settings

SESSION_COOKIE = "llmchat_session"
_ALGORITHM = "HS256"

_password_hash = PasswordHash.recommended()
# Vérifié quand l'e-mail est inconnu, pour que la réponse prenne le même temps.
_DUMMY_HASH = _password_hash.hash("llmchat-dummy-password")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    return _password_hash.verify(password, password_hash or _DUMMY_HASH) and bool(password_hash)


def create_session_token(user_id: int, version: int) -> str:
    settings = get_settings()
    expires = datetime.now(UTC) + timedelta(days=settings.session_days)
    payload = {"sub": str(user_id), "ver": version, "exp": expires}
    return jwt.encode(payload, settings.secret_key, _ALGORITHM)


def read_session_token(token: str) -> tuple[int, int] | None:
    """Identifiant de l'utilisateur et version de session portés par le jeton."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[_ALGORITHM])
        return int(payload["sub"]), int(payload.get("ver", 0))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def encrypt_secret(value: str) -> str:
    return Fernet(get_settings().fernet_key).encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return Fernet(get_settings().fernet_key).decrypt(token.encode()).decode()
