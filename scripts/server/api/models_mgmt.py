# -*- coding: utf-8 -*-
"""
server.api.models_mgmt - LLM Providers and Model Roles management API endpoints.
Provides CRUD for providers, connectivity testing, remote model fetching (anti-CORS proxy),
and role-to-model mapping configuration.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.db import (
    delete_provider,
    get_model_roles,
    get_provider_by_id,
    list_providers,
    save_model_roles,
    save_provider,
)

router = APIRouter(prefix="/api/models", tags=["Model Providers & Roles"])


class ProviderPayload(BaseModel):
    provider_id: Optional[str] = Field(default=None, description="Unique provider ID")
    name: str = Field(..., description="Display name of provider")
    base_url: str = Field(..., description="API Base URL (e.g. https://api.deepseek.com/v1)")
    api_key: Optional[str] = Field(default="", description="API key or token")
    enabled: bool = Field(default=True, description="Whether this provider is enabled")
    models: List[Dict[str, Any]] = Field(default_factory=list, description="List of configured/selected models")
    custom_headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")
    timeout_seconds: int = Field(default=60, description="Request timeout in seconds")


class TestConnectionRequest(BaseModel):
    base_url: str
    api_key: Optional[str] = ""
    timeout_seconds: Optional[int] = 10


class FetchRemoteModelsRequest(BaseModel):
    base_url: str
    api_key: Optional[str] = ""
    timeout_seconds: Optional[int] = 15


class ModelRolesPayload(BaseModel):
    roles: Dict[str, Dict[str, str]] = Field(
        ...,
        description="Mapping from role_key (chat, summary, quant, debate, vision) to {provider_id, model_id}"
    )


@router.get("/providers")
async def get_providers():
    """List all configured LLM providers."""
    providers = list_providers()
    return {"status": "ok", "providers": providers, "total": len(providers)}


@router.post("/providers")
async def upsert_provider(req: ProviderPayload):
    """Create or update a provider."""
    data = req.model_dump()
    saved = save_provider(data)
    return {"status": "ok", "provider": saved}


@router.delete("/providers/{provider_id}")
async def remove_provider(provider_id: str):
    """Delete a provider by provider_id."""
    success = delete_provider(provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "ok", "deleted": provider_id}


@router.post("/test-connection")
async def test_connection(req: TestConnectionRequest):
    """
    Test connectivity and latency for a given BaseURL and API Key.
    Attempts to hit /models or root endpoint with timeout.
    """
    url = req.base_url.strip().rstrip("/")
    if not url:
        raise HTTPException(status_code=400, detail="Base URL 不能为空")

    headers = {"Content-Type": "application/json"}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key.strip()}"

    start_t = time.time()
    test_endpoints = [f"{url}/models", url]

    last_err = ""
    for target in test_endpoints:
        try:
            async with httpx.AsyncClient(timeout=float(req.timeout_seconds or 10)) as client:
                resp = await client.get(target, headers=headers)
                latency_ms = int((time.time() - start_t) * 1000)
                if resp.status_code in (200, 201):
                    return {
                        "status": "ok",
                        "latency_ms": latency_ms,
                        "message": f"连接成功 (HTTP {resp.status_code}, {latency_ms}ms)",
                    }
                elif resp.status_code == 401:
                    return {
                        "status": "error",
                        "latency_ms": latency_ms,
                        "message": "认证失败 (401 Unauthorized)，请检查 API 密钥是否有效",
                    }
                elif resp.status_code in (404, 405):
                    last_err = f"HTTP {resp.status_code}"
                    continue
                else:
                    return {
                        "status": "warning",
                        "latency_ms": latency_ms,
                        "message": f"服务响应异常 (HTTP {resp.status_code}, {latency_ms}ms)",
                    }
        except httpx.ConnectError:
            last_err = f"网络无法连接至目标地址: {target}"
        except httpx.TimeoutException:
            last_err = f"连接超时 ({req.timeout_seconds}s)"
        except Exception as exc:
            last_err = str(exc)

    return {
        "status": "error",
        "latency_ms": int((time.time() - start_t) * 1000),
        "message": f"连接失败: {last_err}",
    }


@router.post("/fetch-remote")
async def fetch_remote_models(req: FetchRemoteModelsRequest):
    """
    Server-side proxy to fetch remote model list from {base_url}/models.
    Bypasses browser CORS policy and standardizes model metadata.
    """
    base = req.base_url.strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="Base URL 不能为空")

    target_url = f"{base}/models"
    headers = {"Content-Type": "application/json"}
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key.strip()}"

    try:
        async with httpx.AsyncClient(timeout=float(req.timeout_seconds or 15)) as client:
            resp = await client.get(target_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"获取模型列表失败 [HTTP {resp.status_code}]: {resp.text[:200]}"
                )
            res_data = resp.json()

            # Handle standard OpenAI /models response format: {"data": [{"id": "xxx"}, ...]}
            raw_models = []
            if isinstance(res_data, dict):
                if "data" in res_data and isinstance(res_data["data"], list):
                    raw_models = res_data["data"]
                elif "models" in res_data and isinstance(res_data["models"], list):
                    raw_models = res_data["models"]
            elif isinstance(res_data, list):
                raw_models = res_data

            parsed_models: List[Dict[str, Any]] = []
            for item in raw_models:
                m_id = item.get("id") or item.get("name") if isinstance(item, dict) else str(item)
                if not m_id:
                    continue
                lower_id = m_id.lower()
                # Infer capabilities from model id
                caps = ["chat"]
                if any(k in lower_id for k in ("vision", "vl", "4o", "gemini", "claude")):
                    caps.append("vision")
                if any(k in lower_id for k in ("r1", "reasoner", "o1", "o3", "thinking", "reasoning")):
                    caps.append("reasoning")
                if any(k in lower_id for k in ("coder", "code", "qwen", "deepseek", "gpt-4")):
                    caps.append("tools")
                if any(k in lower_id for k in ("flash", "mini", "turbo", "small", "nano")):
                    caps.append("fast")

                parsed_models.append({
                    "id": m_id,
                    "name": m_id,
                    "selected": True,
                    "capabilities": caps,
                    "owned_by": item.get("owned_by", "") if isinstance(item, dict) else "",
                })

            return {
                "status": "ok",
                "count": len(parsed_models),
                "models": parsed_models,
            }

    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail=f"无法连接到目标服务: {target_url}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="请求目标服务超时")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"解析模型列表错误: {str(exc)}")


@router.get("/roles")
async def get_roles():
    """Retrieve current model roles mapping."""
    roles = get_model_roles()
    return {"status": "ok", "roles": roles}


@router.post("/roles")
async def update_roles(payload: ModelRolesPayload):
    """Update model roles mapping."""
    saved = save_model_roles(payload.roles)
    return {"status": "ok", "roles": saved}
