from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from app.deps import CurrentUser, SessionDep
from app.models import ProviderKey
from app.providers.base import ProviderError
from app.providers.registry import PROVIDERS
from app.security import decrypt_secret
from app.services.catalog import catalog

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelOut(BaseModel):
    id: str
    name: str
    free: bool
    accepts_images: bool
    context_length: int | None
    input_price: float | None
    output_price: float | None


class ProviderModels(BaseModel):
    provider: str
    label: str
    models: list[ModelOut]
    # Renseigné si la liste n'a pas pu être lue (clé révoquée, fournisseur injoignable).
    error: str | None = None


@router.get("", response_model=list[ProviderModels])
async def list_models(user: CurrentUser, session: SessionDep) -> list[ProviderModels]:
    """Modèles des fournisseurs pour lesquels l'utilisateur a enregistré une clé."""
    rows = session.exec(select(ProviderKey).where(ProviderKey.user_id == user.id)).all()
    by_provider = {row.provider: row for row in rows}
    result = []
    for provider in PROVIDERS.values():
        row = by_provider.get(provider.id)
        if row is None:
            continue
        entry = ProviderModels(provider=provider.id, label=provider.label, models=[])
        try:
            models = await catalog.models_for(
                user.id, provider.id, decrypt_secret(row.key_enc), row.free_only
            )
            entry.models = [ModelOut(**asdict(model)) for model in models]
        except ProviderError as exc:
            entry.error = exc.message
        result.append(entry)
    return result
