# -*- coding: utf-8 -*-
"""
server.api.users - User management CRUD endpoints.

All endpoints here require menu `system` (i.e. system management). The
super-admin user is immutable via these endpoints.
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.crypto import normalize_phone, validate_password_strength
from server.auth.dependencies import AuthContext, require_super_admin
from server.db import (
    _load_user_system_config,
    create_user,
    delete_user,
    get_role_by_id,
    get_user_by_id,
    list_users,
    record_auth_audit,
    update_user,
    update_user_password,
)

router = APIRouter(prefix="/api/users", tags=["User Management"])


class UserCreatePayload(BaseModel):
    username: str = Field(..., description="手机号（登录账号）")
    name: str = Field(..., description="姓名")
    password: str = Field(..., description="初始密码")
    role_id: int = Field(..., description="角色 ID")
    remark: str = Field(default="", description="备注")


class UserUpdatePayload(BaseModel):
    name: Optional[str] = None
    role_id: Optional[int] = None
    status: Optional[int] = Field(default=None, description="1 启用 / 0 停用")
    remark: Optional[str] = None


class ResetPasswordPayload(BaseModel):
    new_password: str = Field(..., description="重置后的新密码")


PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


@router.get("")
async def list_users_endpoint(_: AuthContext = Depends(require_super_admin)):
    """List users. Super admin only."""
    items = list_users()
    return {"status": "ok", "users": items, "total": len(items)}


@router.post("")
async def create_user_endpoint(
    payload: UserCreatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    """Create a regular user. The system intentionally does NOT allow self-registration."""
    phone = normalize_phone(payload.username)
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail={"error": "bad_phone", "message": "请输入合法的 11 位手机号"})
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail={"error": "bad_name", "message": "姓名不能为空"})

    ok, msg = validate_password_strength(payload.password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "weak_password", "message": msg})

    role = get_role_by_id(payload.role_id)
    if not role:
        raise HTTPException(status_code=400, detail={"error": "bad_role", "message": "所选角色不存在"})
    if role.get("code") == "super_admin":
        # 拒绝通过普通接口赋予超级管理员角色
        raise HTTPException(
            status_code=400,
            detail={"error": "role_forbidden", "message": "不允许将超级管理员角色分配给普通用户"},
        )

    existing = __import__("server.db", fromlist=["get_user_by_username"]).get_user_by_username(phone)
    if existing:
        raise HTTPException(status_code=409, detail={"error": "duplicate_user", "message": "该手机号已存在"})

    # 如果未指定角色，使用配置默认角色
    role_id = payload.role_id
    if not role_id:
        cfg = _load_user_system_config() or {}
        default_code = (cfg.get("default_user_role_code") or "researcher").strip()
        default_role = __import__("server.db", fromlist=["get_role_by_code"]).get_role_by_code(default_code)
        role_id = int(default_role["id"]) if default_role else 0

    new_id = create_user(
        username=phone,
        name=payload.name.strip(),
        password=payload.password,
        role_id=role_id,
        remark=payload.remark,
    )
    record_auth_audit(ctx.user_id, ctx.username, "user.create", "success", "", f"创建用户 {phone}")
    return {"status": "ok", "id": new_id}


@router.patch("/{user_id}")
async def update_user_endpoint(
    user_id: int,
    payload: UserUpdatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "用户不存在"})
    if bool(target.get("is_super_admin")):
        raise HTTPException(
            status_code=400,
            detail={"error": "super_admin_immutable", "message": "超级管理员不可通过界面修改"},
        )
    if payload.role_id is not None:
        role = get_role_by_id(payload.role_id)
        if not role:
            raise HTTPException(status_code=400, detail={"error": "bad_role", "message": "所选角色不存在"})
        if role.get("code") == "super_admin":
            raise HTTPException(
                status_code=400,
                detail={"error": "role_forbidden", "message": "不允许赋予超级管理员角色"},
            )
    ok = update_user(
        user_id=user_id,
        name=payload.name,
        role_id=payload.role_id,
        status=payload.status,
        remark=payload.remark,
    )
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "update_failed", "message": "更新失败"})
    record_auth_audit(ctx.user_id, ctx.username, "user.update", "success", "", f"更新用户 {target.get('username')}")
    return {"status": "ok"}


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    payload: ResetPasswordPayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "用户不存在"})
    if bool(target.get("is_super_admin")):
        raise HTTPException(
            status_code=400,
            detail={"error": "super_admin_immutable", "message": "超级管理员密码请修改 config.yaml 配置文件"},
        )
    ok, msg = validate_password_strength(payload.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "weak_password", "message": msg})
    update_user_password(user_id, payload.new_password)
    record_auth_audit(ctx.user_id, ctx.username, "user.reset_password", "success", "", f"重置 {target.get('username')} 密码")
    return {"status": "ok"}


@router.delete("/{user_id}")
async def delete_user_endpoint(
    user_id: int,
    ctx: AuthContext = Depends(require_super_admin),
):
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "用户不存在"})
    if bool(target.get("is_super_admin")):
        raise HTTPException(
            status_code=400,
            detail={"error": "super_admin_immutable", "message": "超级管理员不可在界面删除"},
        )
    if int(user_id) == int(ctx.user_id):
        raise HTTPException(status_code=400, detail={"error": "self_delete_forbidden", "message": "不能删除自己"})
    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "delete_failed", "message": "删除失败"})
    record_auth_audit(ctx.user_id, ctx.username, "user.delete", "success", "", f"删除用户 {target.get('username')}")
    return {"status": "ok"}
