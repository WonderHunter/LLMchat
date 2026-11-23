import base64
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
    Usage,
)

# Plafond de sortie demandé en streaming ; réduit au plafond du modèle s'il est plus bas.
_MAX_OUTPUT_TOKENS = 64000
_FALLBACK_OUTPUT_TOKENS = 4096


def _wire_message(message: ChatMessage) -> dict:
    """Message au format de l'API Messages : les images précèdent le texte."""
    images = message.get("images")
    if not images:
        return {"role": message["role"], "content": message["content"]}
    blocks: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": base64.b64encode(image.data).decode(),
            },
        }
        for image in images
    ]
    if message["content"]:
        blocks.append({"type": "text", "text": message["content"]})
    return {"role": message["role"], "content": blocks}


def _reads_images(model) -> bool:
    # Sans information sur le modèle, on suppose que oui : c'est le cas de tous les modèles actuels.
    capability = getattr(getattr(model, "capabilities", None), "image_input", None)
    return capability.supported if capability is not None else True


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
                accepts_images=_reads_images(model),
                context_length=model.max_input_tokens,
                max_output_tokens=model.max_tokens,
            )
            for model in models
            if getattr(model, "lifecycle", None) != "retired"
        ]

    async def stream_chat(
        self, key: str, model: ModelInfo, messages: list[ChatMessage]
    ) -> AsyncIterator[str | Usage]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [_wire_message(m) for m in messages if m["role"] != "system"]
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
        yield Usage(input_tokens=final.usage.input_tokens, output_tokens=final.usage.output_tokens)
        if final.stop_reason == "refusal":
            raise ProviderError("Le modèle a refusé de répondre à cette demande.")
