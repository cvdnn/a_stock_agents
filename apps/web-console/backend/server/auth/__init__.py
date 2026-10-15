# -*- coding: utf-8 -*-
"""
server.auth - User authentication subsystem.

This package owns all user-system concerns (password hashing, request auth
dependencies, helper utilities). Keeping these in one place avoids circular
imports with `server.db` and `server.api`.
"""
from server.auth.crypto import hash_password, verify_password
from server.auth.dependencies import (
    AuthContext,
    current_user,
    require_auth,
    require_super_admin,
    require_menu,
)

__all__ = [
    "hash_password",
    "verify_password",
    "AuthContext",
    "current_user",
    "require_auth",
    "require_super_admin",
    "require_menu",
]
