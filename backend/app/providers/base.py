from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

ChatMessage = dict[str, str]  # {"role": "user" | "assistant" | "system", "content": "..."}


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    free: bool = False
    context_length: int | None = None
    max_output_tokens: int | None = None
    # Prix en dollars par million de tokens, quand le fournisseur les publie.
    input_price: float | None = None
    output_price: float | None = None


class ProviderError(Exception):
    """Erreur d'un fournisseur, avec un message affichable tel quel à l'utilisateur."""

    code = "provider_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidKey(ProviderError):
    code = "invalid_key"

    def __init__(self, label: str):
        super().__init__(f"La clé {label} est invalide ou a été révoquée.")


class QuotaExceeded(ProviderError):
    code = "quota_exceeded"

    def __init__(self, label: str):
        super().__init__(
            f"Limite de requêtes atteinte chez {label}. Réessayez plus tard ou changez de modèle."
        )


class InsufficientCredit(ProviderError):
    code = "insufficient_credit"

    def __init__(self, label: str):
        super().__init__(f"Crédit insuffisant sur votre compte {label}.")


class ModelUnavailable(ProviderError):
    code = "model_unavailable"

    def __init__(self, label: str):
        super().__init__(f"Ce modèle n'est pas disponible chez {label} avec votre clé.")


class ProviderUnavailable(ProviderError):
    code = "provider_unavailable"

    def __init__(self, label: str):
        super().__init__(f"{label} est injoignable pour le moment.")


class Provider(ABC):
    id: str
    label: str
    keys_url: str

    @abstractmethod
    async def validate_key(self, key: str) -> None:
        """Lève InvalidKey si le fournisseur refuse la clé."""

    @abstractmethod
    async def list_models(self, key: str | None) -> list[ModelInfo]:
        """Modèles de chat utilisables avec cette clé."""

    @abstractmethod
    def stream_chat(
        self, key: str, model: ModelInfo, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        """Génère la réponse morceau par morceau."""
