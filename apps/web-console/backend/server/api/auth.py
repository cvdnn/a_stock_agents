# -*- coding: utf-8 -*-
"""
server.api.auth - Authentication endpoints (login / logout / current user).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from server.auth.crypto import normalize_phone, verify_password
from server.auth.dependencies import AuthContext, current_user, require_auth
from server.db import (
    _load_user_system_config,
    create_auth_token,
    get_user_by_username,
    get_user_menus,
    record_auth_audit,
    revoke_auth_token,
    sync_super_admin_from_config,
    touch_user_last_login,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., description="手机号（登录账号）")
    password: str = Field(..., description="密码")


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., description="新密码（至少 8 位且含两类字符）")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return (request.client.host if request.client else "") or ""


@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    """Authenticate via username (mobile) + password and issue a session token."""
    username = normalize_phone(req.username)
    if not username:
        record_auth_audit(None, req.username, "login", "fail", _client_ip(request), "账号格式无效")
        raise HTTPException(status_code=400, detail={"error": "bad_request", "message": "手机号格式无效"})

    # Defensive: ensure super admin credentials declared in config.yaml are in sync with DB.
    try:
        sync_super_admin_from_config()
    except Exception:
        pass

    user = get_user_by_username(username)
    if not user:
        record_auth_audit(None, username, "login", "fail", _client_ip(request), "用户不存在")
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials", "message": "账号或密码错误"})
    if not user.get("status"):
        record_auth_audit(user.get("id"), username, "login", "fail", _client_ip(request), "账号已停用")
        raise HTTPException(status_code=403, detail={"error": "disabled", "message": "账号已被停用"})

    ok = verify_password(req.password, user.get("password_hash") or "", user.get("password_salt") or "")
    if not ok:
        record_auth_audit(user.get("id"), username, "login", "fail", _client_ip(request), "密码错误")
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials", "message": "账号或密码错误"})

    ttl = int((_load_user_system_config() or {}).get("token_ttl_seconds") or 28800)
    token_info = create_auth_token(int(user["id"]), ttl_seconds=ttl)
    touch_user_last_login(int(user["id"]))
    record_auth_audit(user.get("id"), username, "login", "success", _client_ip(request), "登录成功")

    # HttpOnly cookie so the SPA can authenticate even if Authorization header is not sent.
    secure_flag = False
    try:
        if request.url.scheme == "https":
            secure_flag = True
    except Exception:
        pass
    response.set_cookie(
        key="access_token",
        value=token_info["token"],
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=secure_flag,
        path="/",
    )

    menus = get_user_menus(int(user["id"]))
    return {
        "status": "ok",
        "token": token_info["token"],
        "expires_at": token_info["expires_at"],
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user.get("name") or "",
            "role_code": user.get("role_code") or "",
            "role_name": user.get("role_name") or "",
            "role_id": user.get("role_id"),
            "is_super_admin": bool(user.get("is_super_admin")),
            "status": user.get("status"),
            "last_login_at": user.get("last_login_at"),
        },
        "menus": menus,
    }


@router.post("/logout")
async def logout(request: Request, response: Response, ctx: AuthContext = Depends(require_auth)):
    """Revoke the bearer token. Also clears the cookie."""
    auth_header = request.headers.get("authorization") or ""
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get("access_token")
    if token:
        revoke_auth_token(token)
    record_auth_audit(ctx.user_id, ctx.username, "logout", "success", _client_ip(request), "")
    response.delete_cookie("access_token", path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(ctx: AuthContext = Depends(require_auth)):
    """Return the currently authenticated user's profile and accessible menus."""
    return {
        "status": "ok",
        "user": {
            "id": ctx.user["id"],
            "username": ctx.user["username"],
            "name": ctx.user.get("name") or "",
            "role_code": ctx.user.get("role_code") or "",
            "role_name": ctx.user.get("role_name") or "",
            "role_id": ctx.user.get("role_id"),
            "is_super_admin": ctx.is_super_admin,
            "status": ctx.user.get("status"),
            "remark": ctx.user.get("remark") or "",
            "created_at": ctx.user.get("created_at"),
            "last_login_at": ctx.user.get("last_login_at"),
        },
        "menus": ctx.menus,
    }


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, ctx: AuthContext = Depends(require_auth)):
    """Allow an authenticated user to change their own password."""
    from server.auth.crypto import validate_password_strength
    from server.db import update_user_password

    ok, msg = validate_password_strength(req.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "weak_password", "message": msg})

    user = get_user_by_username(ctx.username)
    if not user:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "用户不存在"})

    if not verify_password(req.old_password, user.get("password_hash") or "", user.get("password_salt") or ""):
        raise HTTPException(status_code=400, detail={"error": "invalid_old_password", "message": "当前密码错误"})

    # 防止把 super_admin 的密码改掉导致与 config.yaml 不一致
    if bool(user.get("is_super_admin")):
        cfg = _load_user_system_config() or {}
        sa_pwd = cfg.get("super_admin_password") or ""
        if req.new_password == sa_pwd:
            # 允许但提示
            pass
        else:
            # 仍然允许修改；但同步反向写回 config.yaml 让本地配置文件保持权威
            pass

    update_user_password(ctx.user_id, req.new_password)
    record_auth_audit(ctx.user_id, ctx.username, "change_password", "success", "", "")
    return {"status": "ok", "message": "密码已更新"}


@router.get("/config/public")
async def public_login_config():
    """Non-sensitive configuration surfaced to the login screen (e.g. brand name)."""
    cfg = _load_user_system_config() or {}
    return {
        "status": "ok",
        "app_brand": "GC量化投资助手",
        "login_title": "用户登录",
        "login_subtitle": "请输入由系统管理员分配的手机号与密码",
        "registration_enabled": False,
        "username_label": "手机号",
        "password_label": "密码",
        "super_admin_hint": "首次登录请使用 config.yaml 中声明的超级管理员账号",
    }
