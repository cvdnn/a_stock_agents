# -*- coding: utf-8 -*-
"""
server.api.models_mgmt - LLM Providers and Model Roles management API endpoints.
Provides CRUD for providers, connectivity testing, remote model fetching (anti-CORS proxy),
and role-to-model mapping configuration.
"""
from __future__ import annotations

import ipaddress
import os
import socket
import time
from urllib.parse import urlparse
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
    api_key: Optional[str] = Field(default=None, description="API key or token")
    clear_api_key: bool = Field(default=False, description="Explicitly remove the stored API key")
    enabled: bool = Field(default=True, description="Whether this provider is enabled")
    models: List[Dict[str, Any]] = Field(default_factory=list, description="List of configured/selected models")
    custom_headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")
    timeout_seconds: int = Field(default=60, description="Request timeout in seconds")


class TestConnectionRequest(BaseModel):
    provider_id: str
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class FetchRemoteModelsRequest(BaseModel):
    provider_id: str
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class TestModelRequest(BaseModel):
    provider_id: str
    model_id: str
    api_key: Optional[str] = Field(default=None, description="Temporary or updated API key")
    base_url: Optional[str] = Field(default=None, description="Temporary or updated Base URL")
    timeout_seconds: int = Field(default=15, ge=1, le=60)


class ModelRolesPayload(BaseModel):
    roles: Dict[str, Dict[str, str]] = Field(
        ...,
        description="Mapping from role_key (chat, summary, quant, debate, vision) to {provider_id, model_id}"
    )


_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}


def _public_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    """Return the browser-safe projection of a provider record."""
    public = {key: value for key, value in provider.items() if key != "api_key"}
    headers = provider.get("custom_headers") or {}
    public["custom_headers"] = {
        str(key): value
        for key, value in headers.items()
        if str(key).lower() not in _SENSITIVE_HEADER_NAMES
    }
    public["has_api_key"] = bool(provider.get("api_key"))
    return public


def _get_enabled_provider(provider_id: str) -> Dict[str, Any]:
    provider = get_provider_by_id(provider_id.strip())
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.get("enabled"):
        raise HTTPException(status_code=409, detail="Provider is disabled")
    return provider


def _get_provider_for_test(provider_id: str) -> Dict[str, Any]:
    provider = get_provider_by_id(provider_id.strip())
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider



def _is_allowed_local_dev(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address, port: int) -> bool:
    """
    受控开发例外放行：
    仅当配置允许本地连接时（A_STOCK_ALLOW_LOCAL_MODELS，默认放行本地测试），
    且目标服务确实为本地环回 (loopback)，且目标端口严格为 11434 (Ollama) 时放行。
    严禁放行非环回的私有内网 IP，杜绝利用 11434 端口对内网资产进行横向探测。
    """
    allow_local = os.getenv("A_STOCK_ALLOW_LOCAL_MODELS", "true").lower() in ("true", "1", "yes")
    return bool(allow_local and ip_obj.is_loopback and port == 11434)


def _validate_provider_base_url(base_url: str) -> str:
    """
    对 Provider Base URL 执行物理 DNS 解析与深度 SSRF 防御拦截：
    1. 协议必须为 http 或 https，且必须包含有效主机名；
    2. 禁止包含内嵌凭据 (username/password)；
    3. 拦截已知云厂商元数据内部探测域名；
    4. 物理 DNS 解析：在发起网络通信前调用 socket.getaddrinfo 获取目标域名绑定的全部 IP；
    5. 遍历检查所有解析出的 IP，命中任何 is_private、is_loopback、is_link_local、is_reserved、is_multicast 时抛出 HTTP 400；
    6. 仅在满足受控本地开发条件（端口严格为 11434 且 IP 为本机 loopback）时方可豁免放行。
    """
    cleaned = base_url.strip().rstrip("/")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Provider Base URL must use HTTP(S)")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Provider Base URL must not contain credentials")

    hostname = parsed.hostname.lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # 常见内部元数据与危险目标阻断
    if hostname in {"metadata.google.internal", "metadata.azure.internal", "instance-data"}:
        raise HTTPException(status_code=400, detail="Provider Base URL target is not allowed")

    # 获取物理解析 IP 集合
    candidate_ips: List[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    is_literal = False
    _FAKE_IP_NET = ipaddress.ip_network("198.18.0.0/15")
    try:
        literal_ip = ipaddress.ip_address(hostname)
        candidate_ips = [literal_ip]
        is_literal = True
    except ValueError:
        try:
            addr_info = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            for item in addr_info:
                ip_str = item[4][0]
                try:
                    candidate_ips.append(ipaddress.ip_address(ip_str))
                except ValueError:
                    continue
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Provider hostname could not be resolved")

    if not candidate_ips:
        raise HTTPException(status_code=400, detail="Provider host resolved to no valid IP addresses")

    # 遍历检查所有物理 IP
    for ip_obj in candidate_ips:
        # TUN 模式代理 (Clash/Surge/Sing-box) 会为公网域名分配 198.18.0.0/15 虚拟 Fake-IP
        if not is_literal and ip_obj in _FAKE_IP_NET:
            continue

        is_restricted = (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        )
        if is_restricted:
            if not _is_allowed_local_dev(ip_obj, port):
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider host resolves to restricted IP: {ip_obj}"
                )

    return cleaned


def _validated_models_url(base_url: str) -> str:
    """Allow saved HTTP(S) providers while rejecting SSRF targets."""
    cleaned = _validate_provider_base_url(base_url)
    return f"{cleaned}/models"


def _validated_chat_url(base_url: str) -> str:
    """Allow saved HTTP(S) providers while rejecting SSRF targets for chat completions."""
    cleaned = _validate_provider_base_url(base_url)
    return f"{cleaned}/chat/completions"


def _provider_headers(provider: Dict[str, Any]) -> Dict[str, str]:
    headers = {str(key): str(value) for key, value in (provider.get("custom_headers") or {}).items()}
    headers.setdefault("Accept", "application/json")
    if provider.get("api_key"):
        headers.setdefault("Authorization", f"Bearer {provider['api_key']}")
    if "openrouter" in (provider.get("base_url") or "").lower():
        headers.setdefault("HTTP-Referer", "http://localhost:6300")
        headers.setdefault("X-Title", "A-Stock Agents")
    return headers


@router.get("/providers")
async def get_providers():
    """List all configured LLM providers."""
    providers = list_providers()
    return {
        "status": "ok",
        "providers": [_public_provider(provider) for provider in providers],
        "total": len(providers),
    }


@router.post("/providers")
async def upsert_provider(req: ProviderPayload):
    """Create or update a provider."""
    data = req.model_dump(exclude_unset=True)
    saved = save_provider(data)
    return {"status": "ok", "provider": _public_provider(saved)}


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
    Test connectivity for a saved provider without accepting browser credentials.
    """
    provider = _get_provider_for_test(req.provider_id)
    target = _validated_models_url(provider.get("base_url", ""))
    headers = _provider_headers(provider)

    start_t = time.time()
    try:
        async with httpx.AsyncClient(timeout=float(req.timeout_seconds), follow_redirects=False) as client:
            resp = await client.get(target, headers=headers)
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="无法连接到提供商服务器，请检查网络或 API 地址")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="请求上游提供商超时，请检查网络或增加超时时间")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="请求上游提供商服务失败")

    latency_ms = int((time.time() - start_t) * 1000)
    if resp.status_code in (200, 201):
        return {"status": "ok", "latency_ms": latency_ms, "message": "连接成功"}
    if resp.status_code in (401, 403):
        raise HTTPException(status_code=502, detail="鉴权失败，请检查 API 密钥是否有效")
    raise HTTPException(status_code=502, detail=f"上游服务响应异常 (HTTP {resp.status_code})")


@router.post("/test-model")
async def test_model(req: TestModelRequest):
    """
    Test whether a specific model of a provider is functional.
    Sends a minimal ping probe to {base_url}/chat/completions.
    """
    provider = get_provider_by_id(req.provider_id.strip())
    # If not found in DB but caller provided base_url and api_key (e.g. newly added provider)
    if not provider:
        if req.base_url:
            provider = {
                "provider_id": req.provider_id,
                "base_url": req.base_url,
                "api_key": req.api_key or "",
                "enabled": True,
                "custom_headers": {},
            }
        else:
            raise HTTPException(status_code=404, detail="Provider not found")

    base_url = (req.base_url or provider.get("base_url", "")).strip()
    target = _validated_chat_url(base_url)
    headers = _provider_headers(provider)
    if req.api_key:
        headers["Authorization"] = f"Bearer {req.api_key.strip()}"

    payload = {
        "model": req.model_id.strip(),
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": False,
    }

    start_t = time.time()
    try:
        async with httpx.AsyncClient(timeout=float(req.timeout_seconds), follow_redirects=False) as client:
            resp = await client.post(target, headers=headers, json=payload)
    except httpx.ConnectError:
        return {"status": "error", "message": "无法连接服务，请检查网络或 API 地址", "model_id": req.model_id}
    except httpx.TimeoutException:
        return {"status": "error", "message": f"请求超时 ({req.timeout_seconds}秒)", "model_id": req.model_id}
    except httpx.HTTPError as e:
        return {"status": "error", "message": f"网络请求异常: {str(e)}", "model_id": req.model_id}

    latency_ms = int((time.time() - start_t) * 1000)

    if resp.status_code in (200, 201):
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "message": f"模型响应正常 ({latency_ms}ms)",
            "model_id": req.model_id,
        }

    # Extract detailed error message from upstream JSON if available
    err_detail = f"HTTP {resp.status_code}"
    try:
        err_json = resp.json()
        if isinstance(err_json, dict):
            if "error" in err_json:
                err_obj = err_json["error"]
                if isinstance(err_obj, dict):
                    err_detail = err_obj.get("message") or err_detail
                elif isinstance(err_obj, str):
                    err_detail = err_obj
            elif "message" in err_json:
                err_detail = err_json["message"]
            elif "detail" in err_json:
                err_detail = err_json["detail"]
    except Exception:
        if resp.text:
            err_detail = resp.text[:120]

    return {
        "status": "error",
        "latency_ms": latency_ms,
        "message": f"可用性检测失败 [{resp.status_code}]: {err_detail}",
        "model_id": req.model_id,
    }


@router.post("/fetch-remote")
async def fetch_remote_models(req: FetchRemoteModelsRequest):
    """
    Server-side proxy to fetch remote model list from {base_url}/models.
    Bypasses browser CORS policy and standardizes model metadata.
    """
    provider = _get_provider_for_test(req.provider_id)
    target_url = _validated_models_url(provider.get("base_url", ""))
    headers = _provider_headers(provider)

    try:
        async with httpx.AsyncClient(timeout=float(req.timeout_seconds), follow_redirects=False) as client:
            resp = await client.get(target_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Provider returned HTTP {resp.status_code}")
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
                    "name": (item.get("name") if isinstance(item, dict) else None) or m_id,
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
        raise HTTPException(status_code=502, detail="Unable to connect to provider")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Provider request timed out")
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(status_code=502, detail="Provider response could not be parsed")


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
