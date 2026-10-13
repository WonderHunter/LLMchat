from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.deps import CurrentUser, SessionDep
from app.models import ProviderKey
from app.providers.base import Provider, ProviderError
from app.providers.registry import PROVIDERS
from app.security import encrypt_secret
from app.services.catalog import OPENROUTER, catalog

router = APIRouter(prefix="/api/keys", tags=["keys"])


class KeyIn(BaseModel):
    key: str = Field(min_length=8, max_length=500)


class KeyOptions(BaseModel):
    free_only: bool


class KeyStatus(BaseModel):
    provider: str
    label: str
    keys_url: str
    has_key: bool
    last4: str | None = None
    # None pour les fournisseurs où le réglage n'a pas de sens.
    free_only: bool | None = None


def _provider(provider_id: str) -> Provider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fournisseur inconnu")
    return provider


def get_key(session: Session, user_id: int, provider_id: str) -> ProviderKey | None:
    return session.exec(
        select(ProviderKey).where(
            ProviderKey.user_id == user_id, ProviderKey.provider == provider_id
        )
    ).first()


def _status(provider: Provider, row: ProviderKey | None) -> KeyStatus:
    is_openrouter = provider.id == OPENROUTER
    return KeyStatus(
        provider=provider.id,
        label=provider.label,
        keys_url=provider.keys_url,
        has_key=row is not None,
        last4=row.last4 if row else None,
        free_only=(row.free_only if row else True) if is_openrouter else None,
    )


@router.get("", response_model=list[KeyStatus])
def list_keys(user: CurrentUser, session: SessionDep) -> list[KeyStatus]:
    rows = session.exec(select(ProviderKey).where(ProviderKey.user_id == user.id)).all()
    by_provider = {row.provider: row for row in rows}
    return [_status(provider, by_provider.get(provider.id)) for provider in PROVIDERS.values()]


@router.put("/{provider_id}", response_model=KeyStatus)
async def set_key(
    provider_id: str, body: KeyIn, user: CurrentUser, session: SessionDep
) -> KeyStatus:
    provider = _provider(provider_id)
    key = body.key.strip()
    try:
        await provider.validate_key(key)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    row = get_key(session, user.id, provider_id) or ProviderKey(
        user_id=user.id, provider=provider_id, key_enc="", last4=""
    )
    row.key_enc = encrypt_secret(key)
    row.last4 = key[-4:]
    session.add(row)
    session.commit()
    session.refresh(row)
    catalog.forget_user(user.id, provider_id)
    return _status(provider, row)


@router.patch("/{provider_id}", response_model=KeyStatus)
def set_options(
    provider_id: str, body: KeyOptions, user: CurrentUser, session: SessionDep
) -> KeyStatus:
    provider = _provider(provider_id)
    if provider_id != OPENROUTER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Réglage réservé à OpenRouter")
    row = get_key(session, user.id, provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune clé enregistrée")
    row.free_only = body.free_only
    session.add(row)
    session.commit()
    session.refresh(row)
    return _status(provider, row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(provider_id: str, user: CurrentUser, session: SessionDep) -> None:
    _provider(provider_id)
    row = get_key(session, user.id, provider_id)
    if row is not None:
        session.delete(row)
        session.commit()
    catalog.forget_user(user.id, provider_id)
