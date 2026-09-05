# -*- coding: utf-8 -*-
"""
server.llm.ollama_provider - Local Ollama LLM provider.
"""
from __future__ import annotations

import os
from typing import Any, Optional
from server.llm.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Local Ollama provider via Ollama's OpenAI-compatible /v1 endpoint."""

    DEFAULT_BASE_URL = "http://localhost:11434/v1"

    def __init__(
        self,
        model_name: str = "qwen2.5:7b",
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs: Any,
    ) -> None:
        url = base_url or os.getenv("OLLAMA_BASE_URL") or self.DEFAULT_BASE_URL
        if not url.endswith("/v1"):
            url = f"{url.rstrip('/')}/v1"
        super().__init__(
            model_name=model_name,
            api_key="ollama",
            base_url=url,
            timeout=timeout,
            **kwargs,
        )
