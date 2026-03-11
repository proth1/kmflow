"""Tests for LLM provider abstraction layer (KMFLOW-7)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm import (
    AnthropicProvider,
    LLMProviderType,
    OllamaProvider,
    StubProvider,
    get_llm_provider,
    reset_provider,
)


class TestStubProvider:
    @pytest.mark.asyncio
    async def test_generate_returns_message(self) -> None:
        provider = StubProvider()
        result = await provider.generate("test prompt")
        assert "not available" in result.lower()

    @pytest.mark.asyncio
    async def test_stream_returns_message(self) -> None:
        provider = StubProvider()
        chunks = []
        async for chunk in provider.generate_stream("test prompt"):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "not available" in chunks[0].lower()

    def test_provider_type(self) -> None:
        provider = StubProvider()
        assert provider.provider_type == LLMProviderType.STUB

    def test_is_local(self) -> None:
        provider = StubProvider()
        assert provider.is_local is True


class TestAnthropicProvider:
    def test_provider_type(self) -> None:
        provider = AnthropicProvider()
        assert provider.provider_type == LLMProviderType.ANTHROPIC

    def test_is_not_local(self) -> None:
        provider = AnthropicProvider()
        assert provider.is_local is False

    @pytest.mark.asyncio
    async def test_generate_calls_anthropic(self) -> None:
        provider = AnthropicProvider(default_model="test-model")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="test response")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_anthropic = MagicMock()
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = await provider.generate("hello", system="be helpful", max_tokens=100)

        assert result == "test response"
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["system"] == "be helpful"
        assert call_kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_generate_with_history(self) -> None:
        provider = AnthropicProvider()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="ok")]

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        mock_anthropic = MagicMock()
        mock_anthropic.AsyncAnthropic.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            result = await provider.generate(
                "new question",
                messages=[{"role": "user", "content": "old q"}, {"role": "assistant", "content": "old a"}],
            )

        assert result == "ok"
        call_kwargs = mock_client.messages.create.call_args[1]
        assert len(call_kwargs["messages"]) == 3  # 2 history + 1 new


class TestOllamaProvider:
    def test_provider_type(self) -> None:
        provider = OllamaProvider()
        assert provider.provider_type == LLMProviderType.OLLAMA

    def test_is_local(self) -> None:
        provider = OllamaProvider()
        assert provider.is_local is True

    @pytest.mark.asyncio
    async def test_generate_calls_ollama_api(self) -> None:
        provider = OllamaProvider(base_url="http://test:11434", default_model="llama3")

        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": "ollama response"}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_httpx = MagicMock()
        mock_httpx.AsyncClient.return_value = mock_client

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await provider.generate("test", system="sys prompt")

        assert result == "ollama response"
        call_args = mock_client.post.call_args
        assert "test:11434/api/chat" in call_args[0][0]
        body = call_args[1]["json"]
        assert body["model"] == "llama3"
        assert body["stream"] is False
        assert len(body["messages"]) == 2  # system + user


class TestGetLLMProvider:
    def setup_method(self) -> None:
        reset_provider()

    def teardown_method(self) -> None:
        reset_provider()

    def test_auto_detect_anthropic_with_key(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "LLM_PROVIDER": ""}):
            provider = get_llm_provider()
            assert provider.provider_type == LLMProviderType.ANTHROPIC

    def test_auto_detect_stub_without_key(self) -> None:
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env["LLM_PROVIDER"] = ""
        with patch.dict(os.environ, env, clear=True):
            provider = get_llm_provider()
            assert provider.provider_type == LLMProviderType.STUB

    def test_explicit_ollama(self) -> None:
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
            provider = get_llm_provider()
            assert provider.provider_type == LLMProviderType.OLLAMA
            assert provider.is_local is True

    def test_explicit_type_argument(self) -> None:
        provider = get_llm_provider(provider_type="stub")
        assert provider.provider_type == LLMProviderType.STUB

    def test_cached_singleton(self) -> None:
        with patch.dict(os.environ, {"LLM_PROVIDER": "stub"}):
            p1 = get_llm_provider()
            reset_provider()
            p2 = get_llm_provider()
            assert p1 is not p2

    def test_env_var_ollama_base_url(self) -> None:
        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://gpu-box:11434"}):
            provider = get_llm_provider()
            assert isinstance(provider, OllamaProvider)
            assert provider._base_url == "http://gpu-box:11434"
