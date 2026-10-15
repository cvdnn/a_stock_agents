# -*- coding: utf-8 -*-
"""
server.api.menus - Menu management endpoints.

Menus are stored in `menus` with `parent_id` to support a tree. The five
top-level entries (投研助手 / 自选个股 / 收益分析 / 技能治理 / 系统管理)
are seeded as built-in and cannot be deleted, but their display name, icon,
and sort order may be edited.
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.auth.dependencies import AuthContext, require_super_admin
from server.db import (
    create_menu,
    delete_menu,
    get_menu_by_id,
    list_menus,
    record_auth_audit,
    update_menu,
)

router = APIRouter(prefix="/api/menus", tags=["Menu Management"])

CODE_RE = re.compile(r"^[a-z][a-z0-9._]{1,63}$")


class MenuCreatePayload(BaseModel):
    code: str = Field(..., description="菜单 code (唯一标识)")
    name: str = Field(..., description="菜单显示名")
    path: str = Field(default="", description="前端路由路径")
    icon: str = Field(default="", description="菜单图标")
    parent_id: int = Field(default=0, description="父菜单 ID (0=顶级)")
    sort_order: int = Field(default=0, description="同级排序")


class MenuUpdatePayload(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    icon: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


@router.get("")
async def list_menus_endpoint(_: AuthContext = Depends(require_super_admin)):
    items = list_menus()
    return {"status": "ok", "menus": items, "total": len(items)}


@router.post("")
async def create_menu_endpoint(
    payload: MenuCreatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    code = (payload.code or "").strip().lower()
    if not CODE_RE.match(code):
        raise HTTPException(
            status_code=400,
            detail={"error": "bad_code", "message": "菜单 code 必须以小写字母开头，仅含小写字母/数字/点/下划线"},
        )
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail={"error": "bad_name", "message": "菜单名称不能为空"})

    existing = [m for m in list_menus() if m.get("code") == code]
    if existing:
        raise HTTPException(status_code=409, detail={"error": "duplicate_code", "message": "菜单 code 已存在"})

    if payload.parent_id:
        parent = get_menu_by_id(payload.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail={"error": "bad_parent", "message": "父菜单不存在"})

    mid = create_menu(
        code=code,
        name=payload.name.strip(),
        path=payload.path.strip(),
        icon=payload.icon.strip(),
        parent_id=int(payload.parent_id or 0),
        sort_order=int(payload.sort_order or 0),
    )
    record_auth_audit(ctx.user_id, ctx.username, "menu.create", "success", "", f"创建菜单 {code}")
    return {"status": "ok", "id": mid}


@router.patch("/{menu_id}")
async def update_menu_endpoint(
    menu_id: int,
    payload: MenuUpdatePayload,
    ctx: AuthContext = Depends(require_super_admin),
):
    menu = get_menu_by_id(menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "菜单不存在"})
    if bool(menu.get("is_builtin")) and payload.parent_id is not None:
        # 顶级内置菜单不允许重新指定父级，避免破坏系统层级
        if int(payload.parent_id) != 0 and int(payload.parent_id) != int(menu.get("parent_id") or 0):
            raise HTTPException(
                status_code=400,
                detail={"error": "builtin_protected", "message": "内置顶级菜单不允许重新指定父级"},
            )

    update_menu(
        menu_id=menu_id,
        name=payload.name,
        path=payload.path,
        icon=payload.icon,
        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
    )
    record_auth_audit(ctx.user_id, ctx.username, "menu.update", "success", "", f"更新菜单 {menu.get('code')}")
    return {"status": "ok"}


@router.delete("/{menu_id}")
async def delete_menu_endpoint(
    menu_id: int,
    ctx: AuthContext = Depends(require_super_admin),
):
    menu = get_menu_by_id(menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "菜单不存在"})
    if bool(menu.get("is_builtin")):
        raise HTTPException(
            status_code=400,
            detail={"error": "builtin_immutable", "message": "内置菜单不可删除"},
        )

    # 删除前检查是否有子菜单
    children = [m for m in list_menus() if int(m.get("parent_id") or 0) == int(menu_id)]
    if children:
        raise HTTPException(
            status_code=400,
            detail={"error": "has_children", "message": f"该菜单仍有 {len(children)} 个子菜单，请先删除子菜单"},
        )

    ok = delete_menu(menu_id)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "delete_failed", "message": "删除失败"})
    record_auth_audit(ctx.user_id, ctx.username, "menu.delete", "success", "", f"删除菜单 {menu.get('code')}")
    return {"status": "ok"}
