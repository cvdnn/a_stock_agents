# -*- coding: utf-8 -*-
"""
server.auth.dependencies - FastAPI dependency injection for auth + RBAC.

Provides:
    - AuthContext: lightweight container returned to handlers
    - current_user: optional current user (no 401 if missing)
    - require_auth: hard requirement that the request is authenticated
    - require_super_admin: only the super admin user is allowed
    - require_menu: gate a route by menu code

The bearer token is stored in the `auth_tokens` table and survives across
requests until expiry or explicit revocation (logout).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from fastapi import Depends, Header, HTTPException, Request, status

from server.db import (
    get_user_by_id,
    get_user_menus,
    lookup_auth_token,
)


@dataclass
class AuthContext:
    user: dict
    menus: List[dict]

    @property
    def user_id(self) -> int:
        return int(self.user.get("id") or 0)

    @property
    def username(self) -> str:
        return str(self.user.get("username") or "")

    @property
    def name(self) -> str:
        return str(self.user.get("name") or "")

    @property
    def role_code(self) -> str:
        return str(self.user.get("role_code") or "")

    @property
    def role_id(self) -> Optional[int]:
        return self.user.get("role_id")

    @property
    def is_super_admin(self) -> bool:
        return bool(self.user.get("is_super_admin"))

    def has_menu(self, code: str) -> bool:
        if self.is_super_admin:
            return True
        return any(m.get("code") == code for m in self.menus)


def _extract_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    """Resolve token from Authorization header first, then cookie `access_token`."""
    if authorization:
        s = authorization.strip()
        if s.lower().startswith("bearer "):
            return s[7:].strip()
        return s
    cookie = request.cookies.get("access_token")
    return cookie or None


def current_user(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Optional[AuthContext]:
    """Best-effort current user (None if no token or invalid)."""
    token = _extract_token(request, authorization)
    if not token:
        return None
    record = lookup_auth_token(token)
    if not record:
        return None
    user = get_user_by_id(int(record["user_id"]))
    if not user or not user.get("status"):
        return None
    menus = get_user_menus(int(user["id"]))
    return AuthContext(user=user, menus=menus)


def require_auth(ctx: Optional[AuthContext] = Depends(current_user)) -> AuthContext:
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "unauthorized", "message": "未登录或登录已过期"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx


def require_super_admin(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
    if not ctx.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "该操作仅限超级管理员"},
        )
    return ctx


def require_menu(code: str):
    """Dependency factory: require the current user to have access to `code`."""

    def _dep(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
        if not ctx.has_menu(code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden", "message": f"无菜单 {code} 的访问权限"},
            )
        return ctx

    return _dep
