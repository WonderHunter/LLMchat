from collections.abc import AsyncIterator

import anthropic
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

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
)

# Plafond de sortie demandé en streaming ; réduit au plafond du modèle s'il est plus bas.
_MAX_OUTPUT_TOKENS = 64000
_FALLBACK_OUTPUT_TOKENS = 4096


class AnthropicProvider(Provider):
    id = "anthropic"
    label = "Anthropic"
    keys_url = "https://platform.claude.com/settings/keys"

    max_retries = 1
    # Transport httpx2 injecté par les tests ; None en fonctionnement normal.
    transport = None

    def _client(self, key: str) -> AsyncAnthropic:
        http_client = DefaultAsyncHttpxClient(transport=self.transport) if self.transport else None
        return AsyncAnthropic(api_key=key, max_retries=self.max_retries, http_client=http_client)

    def _translate(self, exc: Exception) -> ProviderError:
        if isinstance(exc, anthropic.AuthenticationError):
            return InvalidKey(self.label)
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ModelUnavailable(self.label)
        if isinstance(exc, anthropic.NotFoundError):
            return ModelUnavailable(self.label)
        if isinstance(exc, anthropic.RateLimitError):
            return QuotaExceeded(self.label)
        if isinstance(exc, anthropic.BadRequestError):
            # Un solde épuisé arrive en 400, avec ce libellé dans le message.
            if "credit balance" in exc.message.lower():
                return InsufficientCredit(self.label)
            return ProviderError(f"{self.label} a refusé la requête : {exc.message}")
        if isinstance(exc, anthropic.APIStatusError):
            return ProviderError(f"{self.label} a renvoyé une erreur ({exc.status_code}).")
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderUnavailable(self.label)
        return ProviderError(f"{self.label} a renvoyé une erreur inattendue.")

    async def validate_key(self, key: str) -> None:
        try:
            async with self._client(key) as client:
                await client.models.list(limit=1)
        except anthropic.AnthropicError as exc:
            raise self._translate(exc) from exc

    async def list_models(self, key: str | None) -> list[ModelInfo]:
        try:
            async with self._client(key or "") as client:
                models = [model async for model in client.models.list(limit=100)]
        except anthropic.AnthropicError as exc:
            raise self._translate(exc) from exc
        return [
            ModelInfo(
                id=model.id,
                name=model.display_name or model.id,
                context_length=model.max_input_tokens,
                max_output_tokens=model.max_tokens,
            )
            for model in models
            if getattr(model, "lifecycle", None) != "retired"
        ]

    async def stream_chat(
        self, key: str, model: ModelInfo, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        max_tokens = min(model.max_output_tokens or _FALLBACK_OUTPUT_TOKENS, _MAX_OUTPUT_TOKENS)
        try:
            async with self._client(key) as client:
                async with client.messages.stream(
                    model=model.id,
                    max_tokens=max_tokens,
                    messages=turns,
                    **({"system": system} if system else {}),
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
                    final = await stream.get_final_message()
        except anthropic.AnthropicError as exc:
            raise self._translate(exc) from exc
        if final.stop_reason == "refusal":
            raise ProviderError("Le modèle a refusé de répondre à cette demande.")
