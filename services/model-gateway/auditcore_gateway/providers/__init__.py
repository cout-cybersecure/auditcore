"""Provider adapters.

Each provider implements `Provider.complete(messages, model, **kwargs)`.
Providers are constructed lazily by `get_provider(name)` so missing
SDKs/keys only fail for the specific route that needs them.
"""
from __future__ import annotations

from typing import Protocol

from ..types import Message, ModelResponse


class Provider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[Message],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ModelResponse: ...


_PROVIDERS: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> Provider:
    if name not in _PROVIDERS:
        # Lazy import: don't blow up at startup if a provider SDK is missing.
        if name == "anthropic":
            from . import anthropic as _a
            register(_a.AnthropicProvider())
        elif name == "openai":
            from . import openai as _o
            register(_o.OpenAIProvider())
        elif name == "google":
            from . import google as _g
            register(_g.GoogleProvider())
        elif name == "local":
            from . import local as _l
            register(_l.LocalProvider())
        else:
            raise KeyError(f"unknown provider: {name}")
    return _PROVIDERS[name]
