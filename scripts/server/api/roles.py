# -*- coding: utf-8 -*-
"""
server.api.roles - Role management endpoints.

Roles are stored in `roles` and joined to `menus` via `role_menus`. Built-in
roles (超级管理员 / 投研用户) cannot be deleted but their menus may be
edited. The super admin role cannot be assigned to any non-super-admin user.
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.dependencies import AuthContext, require_super_admin
from server.db import (
    create_role,
    delete_role,
    get_role_by_code,
    get_role_by_id,
    get_role_menu_ids,
    list_roles,
    list_users,
    record_auth_audit,
    update_role,
)

router = APIRouter(prefix="/api/roles", tags=["Role Management"])

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


class RoleCreatePayload(BaseModel):
    code: str = Field(..., description="角色英文 code (a-z, 0-9, _)")
    name: str = Field(..., description="角色中文名")
    description: str = Field(default="", description="描述")
    menu_ids: List[int] = Field(default_factory=list, description="授予的菜单 ID 列表")


class RoleUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    menu_ids: Optional[List[int]] = None


@router.get("")
async def list_roles_endpoint(_: AuthContext = Depends(require_super_admin)):
    items = list_roles()
    # attach menu_ids for convenience
    for r in items:
        r["menu_ids"] = get_role_menu_ids(int(r["id"]))
    return {"status": "ok", "roles": items, "total": len(items)}


@router.post("")
async def create_role_endpoint(
    payload: RoleCreatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    code = (payload.code or "").strip().lower()
    if not CODE_RE.match(code):
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_code", "message": "角色 code 必须以小写字母开头，仅含小写字母/数字/下划线，长度 2-32"},
        )
    if code == "super_admin":
        raise HTTPException(
            status_code=400,
            detail={"error": "code_reserved", "message": "不允许创建 code 为 super_admin 的角色"},
        )
    if get_role_by_code(code):
        raise HTTPException(status_code=409, detail={"error": "duplicate_code", "message": "角色 code 已存在"})
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail={"error": "bad_name", "message": "角色名不能为空"})

    rid = create_role(
        code=code,
        name=payload.name.strip(),
        description=payload.description,
        menu_ids=payload.menu_ids,
    )
    record_auth_audit(ctx.user_id, ctx.username, "role.create", "success", "", f"创建角色 {code}")
    return {"status": "ok", "id": rid}


@router.patch("/{role_id}")
async def update_role_endpoint(
    role_id: int,
    payload: RoleUpdatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    role = get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "角色不存在"})

    if role.get("code") == "super_admin" and payload.name is not None and payload.name.strip() != role.get("name"):
        # 允许修改菜单但禁止修改 super_admin 的展示名（避免绕过内置保护）
        if payload.name.strip() != "超级管理员":
            raise HTTPException(
                status_code=400,
                detail={"error": "builtin_immutable", "message": "内置超级管理员角色的展示名不可修改"},
            )

    update_role(
        role_id=role_id,
        name=payload.name,
        description=payload.description,
        menu_ids=payload.menu_ids,
    )
    record_auth_audit(ctx.user_id, ctx.username, "role.update", "success", "", f"更新角色 {role.get('code')}")
    return {"status": "ok"}


@router.delete("/{role_id}")
async def delete_role_endpoint(
    role_id: int,
    ctx: AuthContext = Depends(require_super_admin),
):
    role = get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "角色不存在"})
    if role.get("code") == "super_admin":
        raise HTTPException(
            status_code=400,
            detail={"error": "builtin_immutable", "message": "内置超级管理员角色不可删除"},
        )

    users = [u for u in list_users() if int(u.get("role_id") or 0) == int(role_id)]
    if users:
        raise HTTPException(
            status_code=400,
            detail={"error": "role_in_use", "message": f"仍有 {len(users)} 个用户绑定该角色，无法删除"},
        )

    ok = delete_role(role_id)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "delete_failed", "message": "删除失败"})
    record_auth_audit(ctx.user_id, ctx.username, "role.delete", "success", "", f"删除角色 {role.get('code')}")
    return {"status": "ok"}


@router.get("/{role_id}/menus")
async def get_role_menus(role_id: int, _: AuthContext = Depends(require_super_admin)):
    role = get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "角色不存在"})
    return {"status": "ok", "menu_ids": get_role_menu_ids(role_id)}
