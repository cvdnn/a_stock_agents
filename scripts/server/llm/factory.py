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
    def get_provider(
        model: Optional[str] = None,
        role: Optional[str] = None,
        **kwargs: Any,
    ) -> BaseLLMProvider:
        # 1. Try to resolve via database-configured Model Roles
        from server.db import get_model_roles, get_provider_by_id, list_providers

        target_model = model
        target_provider_id = None

        # Check if role-based lookup requested (e.g. role='chat', 'quant', 'summary', 'debate', 'vision')
        if role:
            roles = get_model_roles()
            if role in roles:
                role_info = roles[role]
                target_provider_id = role_info.get("provider_id")
                target_model = role_info.get("model_id")

        # Check if model has format "model_id|provider_id"
        if target_model and "|" in target_model:
            parts = target_model.split("|", 1)
            target_model = parts[0].strip()
            target_provider_id = parts[1].strip()

        # If a provider_id was resolved or specified, use that DB provider
        if target_provider_id:
            prov_rec = get_provider_by_id(target_provider_id)
            if prov_rec and prov_rec.get("enabled"):
                m_name = target_model or "default"
                b_url = prov_rec.get("base_url", "").strip().rstrip("/")
                key = prov_rec.get("api_key", "").strip()
                t_out = float(prov_rec.get("timeout_seconds") or 60.0)
                
                # If provider is Claude native
                if "anthropic" in b_url.lower() or "claude" in m_name.lower():
                    return ClaudeProvider(
                        model_name=m_name,
                        api_key=key,
                        base_url=b_url or None,
                        timeout=t_out,
                        **kwargs,
                    )
                # If provider is Ollama
                if "11434" in b_url or b_url.endswith("/v1"):
                    return OpenAIProvider(
                        model_name=m_name,
                        api_key=key or "ollama",
                        base_url=b_url,
                        timeout=t_out,
                        **kwargs,
                    )
                # Standard OpenAI-compatible provider (DeepSeek, SiliconFlow, vLLM, OpenAI, etc.)
                return OpenAIProvider(
                    model_name=m_name,
                    api_key=key,
                    base_url=b_url,
                    timeout=t_out,
                    **kwargs,
                )

        # If model is not explicitly provided, check if 'chat' role exists in DB
        if not target_model:
            roles = get_model_roles()
            if "chat" in roles and roles["chat"].get("provider_id"):
                chat_role = roles["chat"]
                prov_rec = get_provider_by_id(chat_role["provider_id"])
                if prov_rec and prov_rec.get("enabled"):
                    m_name = chat_role.get("model_id") or "default"
                    b_url = prov_rec.get("base_url", "").strip().rstrip("/")
                    key = prov_rec.get("api_key", "").strip()
                    t_out = float(prov_rec.get("timeout_seconds") or 60.0)
                    return OpenAIProvider(
                        model_name=m_name,
                        api_key=key,
                        base_url=b_url,
                        timeout=t_out,
                        **kwargs,
                    )

        # Check if target_model matches any active DB provider's configured models
        all_active_providers = [p for p in list_providers() if p.get("enabled")]
        if target_model and all_active_providers:
            for p in all_active_providers:
                p_models = [m.get("id") for m in p.get("models", []) if isinstance(m, dict)]
                if target_model in p_models:
                    return OpenAIProvider(
                        model_name=target_model,
                        api_key=p.get("api_key", ""),
                        base_url=p.get("base_url", ""),
                        timeout=float(p.get("timeout_seconds") or 60.0),
                        **kwargs,
                    )

        # Fallback to Environment Variables & Static Provider resolution
        model_name = (target_model or server_settings.default_model).strip()
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
