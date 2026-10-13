from app.providers.anthropic import AnthropicProvider
from app.providers.base import Provider
from app.providers.openai_compat import OpenAIProvider, OpenRouterProvider

PROVIDERS: dict[str, Provider] = {
    provider.id: provider
    for provider in (OpenRouterProvider(), OpenAIProvider(), AnthropicProvider())
}
