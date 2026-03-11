"""LLM provider abstraction layer (KMFLOW-7).

Routes LLM requests to either a cloud provider (Anthropic Claude) or a
local provider (Ollama, vLLM) based on deployment configuration.  This
enables air-gapped and on-prem deployments where no external API calls
are permitted.

Usage::

    from src.core.llm import get_llm_provider

    llm = get_llm_provider()
    response = await llm.generate("What is KMFlow?", system="You are a helpful assistant.")
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton
_provider: LLMProvider | None = None


class LLMProviderType(StrEnum):
    """Supported LLM provider types."""

    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    STUB = "stub"


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a completion.

        Args:
            prompt: User message text.
            system: Optional system prompt.
            model: Model override (provider-specific).
            max_tokens: Maximum response tokens.
            messages: Optional conversation history (role/content dicts).

        Returns:
            Generated text response.
        """

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a completion token by token.

        Yields:
            Text chunks as they arrive.
        """
        yield ""  # pragma: no cover — abstract

    @property
    @abstractmethod
    def provider_type(self) -> LLMProviderType:
        """Return the provider type for logging and diagnostics."""

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether this provider runs locally (no external API calls)."""


class AnthropicProvider(LLMProvider):
    """Cloud provider using Anthropic Claude API."""

    def __init__(self, default_model: str = "claude-sonnet-4-5-20250929") -> None:
        self._default_model = default_model

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic()
        msgs: list[dict[str, str]] = []
        if messages:
            msgs.extend(messages)
        msgs.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system

        response = await client.messages.create(**kwargs)  # type: ignore[arg-type]
        return response.content[0].text  # type: ignore[union-attr]

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        import anthropic

        client = anthropic.AsyncAnthropic()
        msgs: list[dict[str, str]] = []
        if messages:
            msgs.extend(messages)
        msgs.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system

        async with client.messages.stream(**kwargs) as stream:  # type: ignore[arg-type]
            async for text_chunk in stream.text_stream:
                yield text_chunk

    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.ANTHROPIC

    @property
    def is_local(self) -> bool:
        return False


class OllamaProvider(LLMProvider):
    """Local LLM provider using Ollama HTTP API.

    Compatible with any OpenAI-compatible local inference server
    (Ollama, vLLM, llama.cpp server) by pointing ``base_url`` to
    the appropriate endpoint.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.1:8b",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        import httpx

        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        if messages:
            msgs.extend(messages)
        msgs.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model or self._default_model,
                    "messages": msgs,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        import httpx

        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        if messages:
            msgs.extend(messages)
        msgs.append({"role": "user", "content": prompt})

        import json

        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": model or self._default_model,
                    "messages": msgs,
                    "stream": True,
                    "options": {"num_predict": max_tokens},
                },
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.strip():
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.OLLAMA

    @property
    def is_local(self) -> bool:
        return True


class StubProvider(LLMProvider):
    """Fallback provider that returns canned responses.

    Used when no LLM is configured or available, e.g. in test
    environments or air-gapped deployments without a local model.
    """

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        return (
            "LLM is not available in this deployment configuration. "
            "Please configure an LLM provider (ANTHROPIC_API_KEY for cloud, "
            "or LLM_PROVIDER=ollama with a running Ollama instance for local)."
        )

    async def generate_stream(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 2000,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        yield await self.generate(prompt)

    @property
    def provider_type(self) -> LLMProviderType:
        return LLMProviderType.STUB

    @property
    def is_local(self) -> bool:
        return True


def get_llm_provider(
    provider_type: str | None = None,
    **kwargs: Any,
) -> LLMProvider:
    """Return a cached LLM provider instance.

    Provider selection priority:
    1. Explicit ``provider_type`` argument
    2. ``LLM_PROVIDER`` environment variable
    3. Auto-detect: Anthropic if API key present, else stub

    Args:
        provider_type: One of "anthropic", "ollama", "stub".
        **kwargs: Provider-specific options (base_url, default_model, etc.).
    """
    global _provider  # noqa: PLW0603

    if _provider is not None and provider_type is None:
        return _provider

    import os

    resolved = provider_type or os.environ.get("LLM_PROVIDER", "").lower()

    if resolved == "ollama":
        _provider = OllamaProvider(
            base_url=kwargs.get("base_url", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")),
            default_model=kwargs.get("default_model", os.environ.get("OLLAMA_MODEL", "llama3.1:8b")),
        )
        logger.info("LLM provider: Ollama at %s", _provider._base_url)
    elif resolved == "anthropic" or (not resolved and os.environ.get("ANTHROPIC_API_KEY")):
        _provider = AnthropicProvider(
            default_model=kwargs.get("default_model", "claude-sonnet-4-5-20250929"),
        )
        logger.info("LLM provider: Anthropic Claude")
    else:
        _provider = StubProvider()
        logger.warning("LLM provider: Stub (no provider configured)")

    return _provider


def reset_provider() -> None:
    """Reset the cached provider (used in tests)."""
    global _provider  # noqa: PLW0603
    _provider = None
