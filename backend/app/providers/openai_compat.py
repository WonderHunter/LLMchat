import base64
import re
from collections.abc import AsyncIterator

import httpx
import openai
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.providers.base import (
    ChatMessage,
    InsufficientCredit,
    InvalidKey,
    ModelInfo,
    ModelUnavailable,
    Provider,
    ProviderError,
    ProviderUnavailable,
    QuotaExceeded,
    Usage,
)


def _wire_messages(messages: list[ChatMessage]) -> list[dict]:
    """Messages au format « chat completions » : les images deviennent des URL de données."""
    wired = []
    for message in messages:
        images = message.get("images")
        if not images:
            wired.append({"role": message["role"], "content": message["content"]})
            continue
        parts: list[dict] = (
            [{"type": "text", "text": message["content"]}] if message["content"] else []
        )
        for image in images:
            encoded = base64.b64encode(image.data).decode()
            url = f"data:{image.media_type};base64,{encoded}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        wired.append({"role": message["role"], "content": parts})
    return wired


class OpenAICompatProvider(Provider):
    """Fournisseurs qui parlent le protocole « chat completions » d'OpenAI."""

    base_url: str | None = None
    default_headers: dict[str, str] | None = None
    max_retries = 1
    # Champs ajoutés au corps de la requête de chat, propres à un fournisseur.
    extra_body: dict | None = None
    # Signaler une réponse dont le flux s'est fermé sans dire qu'elle était finie.
    require_finish_reason = False
    # Transport httpx2 injecté par les tests ; None en fonctionnement normal.
    transport = None

    def _client(self, key: str) -> AsyncOpenAI:
        http_client = DefaultAsyncHttpxClient(transport=self.transport) if self.transport else None
        return AsyncOpenAI(
            api_key=key,
            base_url=self.base_url,
            default_headers=self.default_headers,
            max_retries=self.max_retries,
            http_client=http_client,
        )

    def _translate(self, exc: Exception) -> ProviderError:
        if isinstance(exc, openai.AuthenticationError):
            return InvalidKey(self.label)
        if isinstance(exc, openai.RateLimitError):
            if getattr(exc, "code", None) == "insufficient_quota":
                return InsufficientCredit(self.label)
            return QuotaExceeded(self.label)
        if isinstance(exc, openai.NotFoundError):
            return ModelUnavailable(self.label)
        if isinstance(exc, openai.APIStatusError):
            if exc.status_code == 402:
                return InsufficientCredit(self.label)
            if exc.status_code in (400, 422):
                # Requête refusée (trop longue, paramètre non pris en charge…) : le message
                # du fournisseur est le seul à dire pourquoi.
                return ProviderError(f"{self.label} a refusé la requête : {exc.message}")
            return ProviderError(f"{self.label} a renvoyé une erreur ({exc.status_code}).")
        if isinstance(exc, openai.APIConnectionError):
            return ProviderUnavailable(self.label)
        if isinstance(exc, openai.APIError):
            # Erreur envoyée au milieu du flux, une fois la réponse commencée.
            if getattr(exc, "code", None) == "insufficient_quota":
                return InsufficientCredit(self.label)
            return ProviderError(f"{self.label} a interrompu la réponse : {exc.message}")
        return ProviderError(f"{self.label} a renvoyé une erreur inattendue.")

    async def stream_chat(
        self, key: str, model: ModelInfo, messages: list[ChatMessage]
    ) -> AsyncIterator[str | Usage]:
        usage = None
        finished = False
        try:
            async with self._client(key) as client:
                stream = await client.chat.completions.create(
                    model=model.id,
                    messages=_wire_messages(messages),
                    stream=True,
                    # Demande le décompte des tokens, envoyé dans le dernier morceau.
                    stream_options={"include_usage": True},
                    extra_body=self.extra_body,
                )
                async for chunk in stream:
                    if chunk.choices and (text := chunk.choices[0].delta.content):
                        yield text
                    if chunk.choices and chunk.choices[0].finish_reason:
                        finished = True
                    if chunk.usage:
                        usage = Usage(
                            input_tokens=chunk.usage.prompt_tokens,
                            output_tokens=chunk.usage.completion_tokens,
                            # Champ propre à OpenRouter, absent chez OpenAI.
                            cost=getattr(chunk.usage, "cost", None),
                        )
        except openai.OpenAIError as exc:
            raise self._translate(exc) from exc
        if usage:
            yield usage
        if self.require_finish_reason and not finished:
            raise ProviderError(f"La réponse de {self.label} s'est arrêtée avant la fin.")

    async def _list(self, key: str) -> list:
        try:
            async with self._client(key) as client:
                return [model async for model in client.models.list()]
        except openai.OpenAIError as exc:
            raise self._translate(exc) from exc


class OpenAIProvider(OpenAICompatProvider):
    id = "openai"
    label = "OpenAI"
    keys_url = "https://platform.openai.com/api-keys"

    # L'API ne dit ni quels modèles acceptent « chat completions », ni lesquels lisent les
    # images : on se fie au nom. Les modèles récents lisent tous les images, sauf ceux-ci.
    _NO_IMAGES = re.compile(r"^(gpt-3\.5|o1-mini|o1-preview|o3-mini)")
    _CHAT_PREFIX = re.compile(r"^(gpt-|chatgpt-|o\d)")
    _NOT_CHAT = (
        "instruct",
        "audio",
        "realtime",
        "tts",
        "transcribe",
        "image",
        "embedding",
        "moderation",
        "search",
        "codex",
    )

    async def validate_key(self, key: str) -> None:
        await self._list(key)

    async def list_models(self, key: str | None) -> list[ModelInfo]:
        models = [
            model
            for model in await self._list(key or "")
            if self._CHAT_PREFIX.match(model.id) and not any(w in model.id for w in self._NOT_CHAT)
        ]
        models.sort(key=lambda model: model.created or 0, reverse=True)
        return [
            ModelInfo(
                id=model.id, name=model.id, accepts_images=not self._NO_IMAGES.match(model.id)
            )
            for model in models
        ]


class OneMinProvider(OpenAICompatProvider):
    """1min.AI : une seule clé pour des modèles de plusieurs éditeurs, payés en crédits.

    Particularités, d'après sa documentation : tous ses modèles sont texte seul, il ne publie
    pas de prix en dollars, et il demande de ne pas relancer une requête échouée (chaque
    essai réserve des crédits).
    """

    id = "onemin"
    label = "1min.AI"
    keys_url = "https://app.1min.ai/api"
    base_url = "https://api.1min.ai/openai/v1"
    max_retries = 0
    # Une coupure de connexion peut clore le flux sans message d'erreur.
    require_finish_reason = True

    async def validate_key(self, key: str) -> None:
        await self._list(key)

    async def list_models(self, key: str | None) -> list[ModelInfo]:
        models = await self._list(key or "")
        # Regroupés par éditeur (owned_by), puis par nom.
        models.sort(key=lambda model: (getattr(model, "owned_by", "") or "", model.id))
        return [ModelInfo(id=model.id, name=model.id) for model in models]


class OpenRouterProvider(OpenAICompatProvider):
    id = "openrouter"
    label = "OpenRouter"
    keys_url = "https://openrouter.ai/settings/keys"
    base_url = "https://openrouter.ai/api/v1"
    default_headers = {"X-Title": "LLMchat"}
    # Fait figurer le coût réel de la réponse dans le décompte renvoyé.
    extra_body = {"usage": {"include": True}}

    async def _get(self, path: str, key: str | None) -> httpx.Response:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self.base_url}{path}", headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(self.label) from exc
        if response.status_code in (401, 403):
            raise InvalidKey(self.label)
        if response.status_code != 200:
            raise ProviderError(f"{self.label} a renvoyé une erreur ({response.status_code}).")
        return response

    async def validate_key(self, key: str) -> None:
        await self._get("/key", key)

    async def list_models(self, key: str | None) -> list[ModelInfo]:
        """Catalogue complet d'OpenRouter. Il est public : la clé est facultative."""
        data = (await self._get("/models", key)).json()["data"]
        models = []
        for item in data:
            architecture = item.get("architecture") or {}
            outputs = architecture.get("output_modalities") or ["text"]
            if "text" not in outputs:
                continue
            pricing = item.get("pricing") or {}
            models.append(
                ModelInfo(
                    id=item["id"],
                    name=item.get("name") or item["id"],
                    free=item["id"].endswith(":free"),
                    accepts_images="image" in (architecture.get("input_modalities") or []),
                    context_length=item.get("context_length"),
                    max_output_tokens=(item.get("top_provider") or {}).get("max_completion_tokens"),
                    input_price=_per_million(pricing.get("prompt")),
                    output_price=_per_million(pricing.get("completion")),
                )
            )
        return models


def _per_million(price_per_token: str | None) -> float | None:
    try:
        return round(float(price_per_token) * 1_000_000, 4)
    except (TypeError, ValueError):
        return None
