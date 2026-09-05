# -*- coding: utf-8 -*-
"""
server.db - SQLite database persistence for sessions and chat messages.
Uses WAL mode for high concurrency and local data isolation.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.config import server_settings


def _get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_INITIALIZED_PATHS = set()


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or server_settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    resolved_str = str(path.resolve())
    if resolved_str not in _INITIALIZED_PATHS:
        _init_schemas(conn)
        _INITIALIZED_PATHS.add(resolved_str)

    return conn


def _init_schemas(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                meta_json TEXT DEFAULT '{}'
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                thought TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                tool_name TEXT,
                risk_card TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
        """)


def init_db(db_path: Optional[Path] = None) -> None:
    """Explicitly initialize database schemas if not already created."""
    conn = get_connection(db_path)
    conn.close()



def check_db_health(db_path: Optional[Path] = None) -> bool:
    """Verify database connection can execute queries."""
    try:
        conn = get_connection(db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            row = cur.fetchone()
            return bool(row and row[0] == 1)
        finally:
            conn.close()
    except Exception:
        return False


def create_session(
    title: Optional[str] = None,
    model: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create a new session record."""
    sid = session_id or f"sess_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    now = _get_utc_now_iso()
    session_title = title or f"会话 {sid[-6:]}"
    selected_model = model or server_settings.default_model
    meta_dict = meta or {}
    meta_json = json.dumps(meta_dict, ensure_ascii=False)

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, title, model, created_at, updated_at, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sid, session_title, selected_model, now, now, meta_json),
            )
    finally:
        conn.close()

    return {
        "session_id": sid,
        "title": session_title,
        "model": selected_model,
        "created_at": now,
        "updated_at": now,
        "meta": meta_dict,
    }


def get_session(session_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve session details by ID."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        meta = {}
        if row["meta_json"]:
            try:
                meta = json.loads(row["meta_json"])
            except Exception:
                meta = {}
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "model": row["model"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "meta": meta,
        }
    finally:
        conn.close()


def list_sessions(limit: int = 50, offset: int = 0, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List sessions ordered by updated_at descending."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = cur.fetchall()
        results = []
        for r in rows:
            meta = {}
            if r["meta_json"]:
                try:
                    meta = json.loads(r["meta_json"])
                except Exception:
                    pass
            results.append({
                "session_id": r["session_id"],
                "title": r["title"],
                "model": r["model"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "meta": meta,
            })
        return results
    finally:
        conn.close()


def delete_session(session_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete session and associated messages."""
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def update_session_title(session_id: str, title: str, db_path: Optional[Path] = None) -> bool:
    """Update session title and touch updated_at."""
    conn = get_connection(db_path)
    now = _get_utc_now_iso()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, now, session_id),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def add_message(
    session_id: str,
    role: str,
    content: str,
    thought: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    risk_card: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Store a message in session history and update session updated_at timestamp."""
    now = _get_utc_now_iso()
    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    risk_card_json = json.dumps(risk_card, ensure_ascii=False) if risk_card else None

    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO messages (
                    session_id, role, content, thought, tool_calls,
                    tool_call_id, tool_name, risk_card, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    thought,
                    tool_calls_json,
                    tool_call_id,
                    tool_name,
                    risk_card_json,
                    now,
                ),
            )
            msg_id = cur.lastrowid
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
    finally:
        conn.close()

    return {
        "id": msg_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "thought": thought,
        "tool_calls": tool_calls,
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "risk_card": risk_card,
        "created_at": now,
    }


def get_messages(
    session_id: str,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve message history for a session ordered chronologically."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = cur.fetchall()
        msgs = []
        for r in rows:
            tc = json.loads(r["tool_calls"]) if r["tool_calls"] else None
            rc = json.loads(r["risk_card"]) if r["risk_card"] else None
            msgs.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "thought": r["thought"],
                "tool_calls": tc,
                "tool_call_id": r["tool_call_id"],
                "tool_name": r["tool_name"],
                "risk_card": rc,
                "created_at": r["created_at"],
            })
        return msgs
    finally:
        conn.close()
