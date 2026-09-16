# -*- coding: utf-8 -*-
"""
server.auth.crypto - Password hashing utilities (PBKDF2-HMAC-SHA256).

We avoid pulling new third-party dependencies; Python's stdlib `hashlib` and
`secrets` are sufficient for the local single-tenant deployment described in
the project specification.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Tuple

# Iteration count: read from config if available, otherwise a safe default.
_DEFAULT_ITERATIONS = 120_000


def _get_iterations() -> int:
    try:
        from server.db import _load_user_system_config  # local import to avoid cycles
        cfg = _load_user_system_config() or {}
        n = int(cfg.get("password_iterations") or _DEFAULT_ITERATIONS)
        if n < 10_000:
            n = _DEFAULT_ITERATIONS
        return n
    except Exception:
        return _DEFAULT_ITERATIONS


def hash_password(password: str) -> Tuple[str, str]:
    """Generate a salted PBKDF2-HMAC-SHA256 hash for the given plaintext password.

    Returns:
        (hash_hex, salt_hex)
    """
    if not password:
        raise ValueError("password must be non-empty")
    salt = secrets.token_bytes(16)
    iterations = _get_iterations()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return dk.hex(), salt.hex()


def verify_password(password: str, stored_hash_hex: str, stored_salt_hex: str) -> bool:
    """Constant-time comparison of an attempted password against stored hash."""
    if not password or not stored_hash_hex or not stored_salt_hex:
        return False
    try:
        salt = bytes.fromhex(stored_salt_hex)
        iterations = _get_iterations()
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate.hex(), stored_hash_hex.lower())
    except Exception:
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Return (ok, message). Enforces a minimum local-deployment policy."""
    if not password:
        return False, "密码不能为空"
    if len(password) < 8:
        return False, "密码长度至少 8 位"
    if len(password) > 64:
        return False, "密码长度不能超过 64 位"
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes < 2:
        return False, "密码需包含大小写字母、数字、符号中至少两类"
    return True, "ok"


def normalize_phone(phone: str) -> str:
    """Lightweight normalization for Chinese mobile phone numbers."""
    if not phone:
        return ""
    s = "".join(ch for ch in str(phone).strip() if ch.isdigit())
    if s.startswith("86") and len(s) == 13:
        s = s[2:]
    return s
