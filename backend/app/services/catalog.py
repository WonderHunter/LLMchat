import asyncio
import logging
import time

from app.config import get_settings
from app.providers.base import ModelInfo, ProviderError
from app.providers.registry import PROVIDERS

logger = logging.getLogger(__name__)

OPENROUTER = "openrouter"
_USER_CACHE_SECONDS = 3600


class Catalog:
    """Modèles proposés aux utilisateurs.

    Le catalogue OpenRouter est public et partagé : il est rafraîchi en tâche de fond.
    Ceux d'OpenAI et d'Anthropic dépendent de la clé de chacun : ils sont lus à la demande
    avec la clé de l'utilisateur, puis gardés une heure.
    """

    def __init__(self) -> None:
        self._openrouter: list[ModelInfo] = []
        self._per_user: dict[tuple[int, str], tuple[float, list[ModelInfo]]] = {}

    async def refresh_openrouter(self) -> None:
        models = await PROVIDERS[OPENROUTER].list_models(get_settings().openrouter_service_key)
        if models:
            self._openrouter = models

    async def run_forever(self, interval_minutes: int) -> None:
        while True:
            try:
                await self.refresh_openrouter()
            except ProviderError as exc:
                # On garde la dernière liste connue.
                logger.warning("Catalogue OpenRouter non rafraîchi : %s", exc.message)
            await asyncio.sleep(interval_minutes * 60)

    async def models_for(
        self, user_id: int, provider: str, key: str, free_only: bool
    ) -> list[ModelInfo]:
        if provider == OPENROUTER:
            if not self._openrouter:
                await self.refresh_openrouter()
            return [m for m in self._openrouter if m.free or not free_only]

        cached = self._per_user.get((user_id, provider))
        if cached and cached[0] > time.monotonic():
            return cached[1]
        models = await PROVIDERS[provider].list_models(key)
        self._per_user[(user_id, provider)] = (time.monotonic() + _USER_CACHE_SECONDS, models)
        return models

    async def find(
        self, user_id: int, provider: str, key: str, free_only: bool, model_id: str
    ) -> ModelInfo | None:
        """Le modèle demandé, s'il fait partie de ceux que l'utilisateur a le droit d'utiliser."""
        models = await self.models_for(user_id, provider, key, free_only)
        return next((m for m in models if m.id == model_id), None)

    def forget_user(self, user_id: int, provider: str) -> None:
        self._per_user.pop((user_id, provider), None)

    def clear(self) -> None:
        self._openrouter = []
        self._per_user.clear()


catalog = Catalog()
