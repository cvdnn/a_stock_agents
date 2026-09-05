# -*- coding: utf-8 -*-
"""
server.llm.factory - Factory for creating LLM provider instances.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from server.config import server_settings
from server.llm.base import BaseLLMProvider
from server.llm.claude_provider import ClaudeProvider
from server.llm.gemini_provider import GeminiProvider
from server.llm.mock_provider import MockLLMProvider
from server.llm.ollama_provider import OllamaProvider
from server.llm.openai_provider import OpenAIProvider

logger = logging.getLogger("server.llm.factory")


class LLMProviderFactory:
    """Factory to resolve and instantiate the appropriate LLM provider."""

    @staticmethod
    def get_provider(model: Optional[str] = None, **kwargs: Any) -> BaseLLMProvider:
        model_name = (model or server_settings.default_model).strip()
        lower_name = model_name.lower()

        # Explicit Mock requested
        if lower_name == "mock" or lower_name.startswith("mock-"):
            return MockLLMProvider(model_name=model_name, **kwargs)

        # DeepSeek Models
        if "deepseek" in lower_name:
            if not server_settings.deepseek_api_key:
                logger.warning(
                    "DEEPSEEK_API_KEY not configured. Falling back to MockLLMProvider."
                )
                return MockLLMProvider(model_name=model_name, **kwargs)
            return OpenAIProvider(
                model_name=model_name,
                api_key=server_settings.deepseek_api_key,
                base_url=server_settings.deepseek_base_url,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # OpenAI Models
        if any(prefix in lower_name for prefix in ("gpt-", "o1-", "o3-", "text-embedding")):
            if not server_settings.openai_api_key:
                logger.warning(
                    "OPENAI_API_KEY not configured. Falling back to MockLLMProvider."
                )
                return MockLLMProvider(model_name=model_name, **kwargs)
            return OpenAIProvider(
                model_name=model_name,
                api_key=server_settings.openai_api_key,
                base_url=server_settings.openai_base_url,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # Gemini Models
        if "gemini" in lower_name:
            if not server_settings.gemini_api_key:
                logger.warning(
                    "GEMINI_API_KEY not configured. Falling back to MockLLMProvider."
                )
                return MockLLMProvider(model_name=model_name, **kwargs)
            return GeminiProvider(
                model_name=model_name,
                api_key=server_settings.gemini_api_key,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # Claude Models
        if "claude" in lower_name:
            if not server_settings.anthropic_api_key:
                logger.warning(
                    "ANTHROPIC_API_KEY not configured. Falling back to MockLLMProvider."
                )
                return MockLLMProvider(model_name=model_name, **kwargs)
            return ClaudeProvider(
                model_name=model_name,
                api_key=server_settings.anthropic_api_key,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # Ollama / Local Models
        if lower_name.startswith("ollama/") or lower_name.startswith("local/"):
            clean_name = model_name.split("/", 1)[1]
            return OllamaProvider(
                model_name=clean_name,
                base_url=server_settings.ollama_base_url,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # If user configured an OpenAI key or base url, try OpenAI provider
        if server_settings.openai_api_key:
            return OpenAIProvider(
                model_name=model_name,
                api_key=server_settings.openai_api_key,
                base_url=server_settings.openai_base_url,
                timeout=server_settings.request_timeout,
                **kwargs,
            )

        # Final safe fallback: Mock Provider
        logger.warning(
            f"No specific provider matched for '{model_name}'. Falling back to MockLLMProvider."
        )
        return MockLLMProvider(model_name=model_name, **kwargs)
