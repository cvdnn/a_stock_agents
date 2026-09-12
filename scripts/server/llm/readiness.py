from __future__ import annotations

from urllib.parse import urlparse

import httpx

from server.llm.errors import LLMReadinessError


def is_local_endpoint(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def validate_provider_record(record: dict, model_id: str, require_tools: bool) -> None:
    provider_id = record.get("provider_id")
    if not record.get("enabled"):
        raise LLMReadinessError(
            "LLM_NOT_CONFIGURED", "模型供应商未启用", provider_id=provider_id, model_id=model_id
        )
    base_url = str(record.get("base_url") or "").strip()
    if not base_url:
        raise LLMReadinessError(
            "LLM_NOT_CONFIGURED", "模型供应商缺少 Base URL", provider_id=provider_id, model_id=model_id
        )
    models = [item for item in record.get("models", []) if isinstance(item, dict)]
    selected = next((item for item in models if item.get("id") == model_id), None)
    if models and selected is None:
        raise LLMReadinessError(
            "LLM_MODEL_UNAVAILABLE", "所选模型不在供应商模型列表中", provider_id=provider_id, model_id=model_id
        )
    if require_tools and selected is not None and "tools" not in selected.get("capabilities", []):
        raise LLMReadinessError(
            "LLM_CAPABILITY_UNSUPPORTED", "所选模型未声明工具调用能力", provider_id=provider_id, model_id=model_id
        )
    if not str(record.get("api_key") or "").strip() and not is_local_endpoint(base_url):
        raise LLMReadinessError(
            "LLM_NOT_CONFIGURED", "模型供应商缺少后端 API 密钥", provider_id=provider_id, model_id=model_id
        )


def classify_provider_error(exc: Exception) -> LLMReadinessError:
    if isinstance(exc, LLMReadinessError):
        return exc
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return LLMReadinessError("LLM_TIMEOUT", "模型请求超时")
    message = str(exc)
    if "401" in message or "403" in message:
        return LLMReadinessError("LLM_AUTH_FAILED", "模型供应商认证失败")
    if "404" in message:
        return LLMReadinessError("LLM_MODEL_UNAVAILABLE", "模型不可用")
    if "429" in message or "rate" in message.lower():
        return LLMReadinessError("LLM_TIMEOUT", "模型请求过于频繁或超出配额")
    return LLMReadinessError("LLM_MODEL_UNAVAILABLE", "模型请求失败")

