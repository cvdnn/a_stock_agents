# -*- coding: utf-8 -*-
"""
server.llm.gemini_provider - Google Gemini provider implementation.
Supports Gemini 1.5/2.0 models via Google's OpenAI-compatible endpoint and AI Studio.
"""
from __future__ import annotations

import os
from typing import Any, Optional
from server.llm.openai_provider import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    """Google Gemini provider utilizing Gemini's official OpenAI-compatible endpoint."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

    def __init__(
        self,
        model_name: str = "gemini-1.5-flash",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY") or ""
        url = base_url or os.getenv("GEMINI_BASE_URL") or self.DEFAULT_BASE_URL
        # Normalize model name if prefixed with models/
        clean_model = model_name.replace("models/", "")
        super().__init__(
            model_name=clean_model,
            api_key=key,
            base_url=url,
            timeout=timeout,
            **kwargs,
        )
