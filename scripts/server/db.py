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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                key TEXT,
                content TEXT NOT NULL,
                meta_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_session ON session_memories(session_id, memory_type, id);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                tokens INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_skill_audit ON skill_audit_logs(skill_id, created_at);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_overrides (
                skill_id TEXT PRIMARY KEY,
                enabled INTEGER,
                timeout_seconds INTEGER,
                require_confirmation INTEGER,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_records (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL DEFAULT 0.0,
                status_message TEXT DEFAULT '',
                params_json TEXT DEFAULT '{}',
                result_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                elapsed_ms INTEGER DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON task_records(status, created_at);
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_providers (
                provider_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                api_key TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                models_json TEXT DEFAULT '[]',
                custom_headers_json TEXT DEFAULT '{}',
                timeout_seconds INTEGER DEFAULT 60,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_model_roles (
                role_key TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        _seed_initial_sessions(conn)


def _seed_initial_sessions(conn: sqlite3.Connection) -> None:
    """Pre-seed classic high-quality research sessions if database is empty."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions;")
        row = cur.fetchone()
        if row and row[0] > 0:
            return

        now = _get_utc_now_iso()
        seeds = [
            {
                "id": "s1",
                "title": "A股大盘反弹持续性与放量研判",
                "user_prompt": "结合今日两市放量动能与板块轮动，深度研判上证指数与创业板反弹持续性。",
                "assistant_response": "### 📈 A股大盘行情与反弹持续性综合研判\n\n- **两市量能**：今日全市场放量成交明显，主力资金在核心成长与金融防守板块呈现净回流态势；\n- **均线与形态**：上证指数站稳 20 日均线生命线，MACD 出现零轴上方金叉共振；\n- **主线轮动**：半导体算力链与高股息红利板块形成防守反击双主线；\n- **风控纪律**：按工作区实战铁律严格执行 T0(-3%)/T1(-5%)/T2(-8%) 三级止损，避免盲目追高连板高标。",
                "memory": "大盘放量突破20日均线，多空辩论决议看多，主线聚焦半导体算力与红利防守。",
                "key": "astock-data-feed",
            },
            {
                "id": "s2",
                "title": "宁德时代300750资金面与底背离诊断",
                "user_prompt": "帮我诊断宁德时代 300750 的资金面、主力控盘度及日K线水下二次金叉或底背离形态。",
                "assistant_response": "### 🔋 宁德时代 (300750) 深度量化研报\n\n- **技术形态**：日K级别在零轴下方形成标准的 **MACD 底背离 + 二次金叉** 经典双底结构，空头动能衰竭；\n- **资金与筹码**：主力控盘集中度提升至 72.4%，下方 180~185 元支撑平台构筑坚实密集成交区；\n- **量化评分**：综合 5A 量价与基本面评分 **86.5 分**，具备波段试错条件；\n- **实战动作**：建议在回踩 5 日均线附近分批挂单试错，跌破支撑位即刻启动防守对冲。",
                "memory": "宁德时代(300750): 现价 192.50, 量化总分 86.5分, 确认日K底背离金叉共振。",
                "key": "astock-strategy-macd",
            },
            {
                "id": "s3",
                "title": "5A多因子量化选股与主线轮动模型",
                "user_prompt": "运行 5A 五维共振多因子选股流水线，筛选全市场高夏普比率、低波动且主线动量靠前的标的。",
                "assistant_response": "### 🎯 5A 多因子全市场选股初选结果\n\n经过量价、基本面、估值、资金与主线 5 维正交因子计算与 MAD 去极值：\n1. **比亚迪 (002594)**：总分 91.2 分（主线新能源龙头，出海动量强劲）\n2. **海光信息 (688041)**：总分 88.6 分（国产算力主力深度介入）\n3. **长江电力 (600900)**：总分 87.8 分（高股息红利防御基石）\n4. **中芯国际 (688981)**：总分 86.0 分（半导体晶圆制造自主可控）\n\n已完成样本外滚动回测与目标波动率仓位分配测算。",
                "memory": "5A多因子选股完成，初选入围 4 只核心标的(比亚迪/海光信息/长江电力/中芯国际)。",
                "key": "astock-screener-5a",
            },
            {
                "id": "s4",
                "title": "半导体与CPO算力链短线买点筛查",
                "user_prompt": "梳理今日半导体与 CPO 光模块板块的短线异动，寻找符合退哥短线规则的回踩买点。",
                "assistant_response": "### ⚡ 半导体与算力链短线战法筛查\n\n- **中际旭创 (300308)**：放量突破前高平台后缩量回踩 5 日线，符合龙头首阴与趋势回踩战法；\n- **寒武纪 (688256)**：日内分时承接有力，主力大单净流入显著；\n- **交易纪律**：短线接力仓位控制在 20% 以内，若盘中跌破开盘价立即按 T0 警戒线观望。",
                "memory": "算力CPO板块筛查完成，中际旭创(300308)符合趋势回踩买点。",
                "key": "astock-strategy-tuige",
            },
            {
                "id": "s5",
                "title": "水下二次金叉战法验证与保本价精算",
                "user_prompt": "精算贵州茅台 600519 买入成本 1500 元、100 股的最低税费保本卖出价与三级风控阶梯。",
                "assistant_response": "### 🛡️ 贵州茅台 (600519) 精确保本价与三级止损动作单\n\n严格执行工作区 `AGENTS.md` 铁律，印花税 0.05%、佣金万2.5（最低5元）、过户费，全部向上进位至分位（`math.ceil`）：\n- **买入成本**：¥1,500.00 (共 100 股，本金 ¥150,000.00)\n- **最低保本卖出价**：**¥1,501.16**\n- **三级风控止损阶梯**：\n  - **T0 警戒线 (-3%)**：¥1,455.00（准备对冲防守）\n  - **T1 减仓线 (-5%)**：¥1,425.00（无条件减仓 50%）\n  - **T2 绝杀线 (-8%)**：¥1,380.00（坚决清仓止损出局）",
                "memory": "贵州茅台(600519): 买入成本 1500.00, 最低保本卖出价 1501.16, 止损T0 1455.00。",
                "key": "astock-action-execution",
            },
        ]

        for s in seeds:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, model, created_at, updated_at, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
                (s["id"], s["title"], "deepseek-chat", now, now, json.dumps({"tab": "dashboard"})),
            )
            conn.execute(
                "INSERT OR IGNORE INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (s["id"], "user", s["user_prompt"], now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (s["id"], "assistant", s["assistant_response"], now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO session_memories (session_id, memory_type, key, content, meta_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (s["id"], "task_result", s["key"], s["memory"], json.dumps({"status": "success"}), now),
            )
    except Exception:
        pass



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


def update_session_model(session_id: str, model: str, db_path: Optional[Path] = None) -> bool:
    """Update session model and touch updated_at."""
    conn = get_connection(db_path)
    now = _get_utc_now_iso()
    try:
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET model = ?, updated_at = ? WHERE session_id = ?",
                (model, now, session_id),
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
    """Retrieve message history for a session ordered chronologically (latest `limit` records)."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM (
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
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


# ── Session Memory Persistence ───────────────────────────────────────────────

def add_session_memory(
    session_id: str,
    memory_type: str,
    content: str,
    key: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Store an atomic session memory record (task result, entity preference, conversation fact)."""
    now = _get_utc_now_iso()
    meta_dict = meta or {}
    meta_json = json.dumps(meta_dict, ensure_ascii=False)

    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO session_memories (session_id, memory_type, key, content, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, memory_type, key, content, meta_json, now),
            )
            memory_id = cur.lastrowid
            # Also touch the session's updated_at timestamp
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
    finally:
        conn.close()

    return {
        "id": memory_id,
        "session_id": session_id,
        "memory_type": memory_type,
        "key": key,
        "content": content,
        "meta": meta_dict,
        "created_at": now,
    }


def get_session_memories(
    session_id: str,
    memory_type: Optional[str] = None,
    limit: int = 100,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Retrieve structured memory records for a session, ordered chronologically."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        if memory_type:
            cur.execute(
                """
                SELECT * FROM session_memories
                WHERE session_id = ? AND memory_type = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, memory_type, limit),
            )
        else:
            cur.execute(
                """
                SELECT * FROM session_memories
                WHERE session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, limit),
            )
        rows = cur.fetchall()
        memories = []
        for r in rows:
            meta = {}
            if r["meta_json"]:
                try:
                    meta = json.loads(r["meta_json"])
                except Exception:
                    meta = {}
            memories.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "memory_type": r["memory_type"],
                "key": r["key"],
                "content": r["content"],
                "meta": meta,
                "created_at": r["created_at"],
            })
        return memories
    finally:
        conn.close()


def delete_session_memories(session_id: str, db_path: Optional[Path] = None) -> int:
    """Delete all memories associated with a session."""
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute("DELETE FROM session_memories WHERE session_id = ?", (session_id,))
            return cur.rowcount
    finally:
        conn.close()


# ── Skill Governance Persistence ─────────────────────────────────────────────

def record_skill_audit(
    skill_id: str,
    action: str,
    status: str,
    latency_ms: int = 0,
    error_message: Optional[str] = None,
    tokens: int = 0,
    db_path: Optional[Path] = None,
) -> int:
    """Record an audit log entry for a skill invocation."""
    now = _get_utc_now_iso()
    conn = get_connection(db_path)
    try:
        with conn:
            cur = conn.execute(
                """
                INSERT INTO skill_audit_logs (skill_id, action, status, latency_ms, error_message, tokens, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (skill_id, action, status, latency_ms, error_message, tokens, now),
            )
            return cur.lastrowid or 0
    finally:
        conn.close()


def get_skill_audit_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calculate aggregated calling metrics and per-skill statistics."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM skill_audit_logs;")
        total_calls = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*) FROM skill_audit_logs
            WHERE date(created_at) = date('now');
            """
        )
        today_calls = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM skill_audit_logs WHERE status = 'success';")
        success_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM skill_audit_logs WHERE status != 'success';")
        error_count = cur.fetchone()[0]

        cur.execute("SELECT AVG(latency_ms) FROM skill_audit_logs;")
        avg_latency = float(cur.fetchone()[0] or 0.0)

        # Approximate P95 latency
        cur.execute("SELECT latency_ms FROM skill_audit_logs ORDER BY latency_ms ASC;")
        latencies = [r[0] for r in cur.fetchall()]
        p95_latency = 0
        if latencies:
            idx = int(len(latencies) * 0.95)
            p95_latency = latencies[min(idx, len(latencies) - 1)]

        # Per skill breakdown
        cur.execute(
            """
            SELECT skill_id,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                   SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as error,
                   AVG(latency_ms) as avg_lat,
                   MAX(created_at) as last_called
            FROM skill_audit_logs
            GROUP BY skill_id;
            """
        )
        by_skill = {}
        for r in cur.fetchall():
            by_skill[r["skill_id"]] = {
                "total_calls": r["total"],
                "success_count": r["success"],
                "error_count": r["error"],
                "avg_latency_ms": round(r["avg_lat"] or 0, 1),
                "last_called_at": r["last_called"],
            }

        error_rate = round(error_count / total_calls, 4) if total_calls > 0 else 0.0

        return {
            "total_calls": total_calls,
            "today_calls": today_calls,
            "success_count": success_count,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_latency_ms": round(avg_latency, 1),
            "p95_latency_ms": p95_latency,
            "by_skill": by_skill,
        }
    finally:
        conn.close()


def save_skill_override(
    skill_id: str,
    enabled: Optional[bool] = None,
    timeout_seconds: Optional[int] = None,
    require_confirmation: Optional[bool] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Save persistent configuration override for a skill."""
    now = _get_utc_now_iso()
    conn = get_connection(db_path)
    try:
        with conn:
            # Check existing
            cur = conn.execute("SELECT * FROM skill_overrides WHERE skill_id = ?;", (skill_id,))
            existing = cur.fetchone()
            if existing:
                cur_en = existing["enabled"] if enabled is None else (1 if enabled else 0)
                cur_to = existing["timeout_seconds"] if timeout_seconds is None else timeout_seconds
                cur_rc = existing["require_confirmation"] if require_confirmation is None else (1 if require_confirmation else 0)
                conn.execute(
                    """
                    UPDATE skill_overrides
                    SET enabled = ?, timeout_seconds = ?, require_confirmation = ?, updated_at = ?
                    WHERE skill_id = ?;
                    """,
                    (cur_en, cur_to, cur_rc, now, skill_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO skill_overrides (skill_id, enabled, timeout_seconds, require_confirmation, updated_at)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (
                        skill_id,
                        (1 if enabled else 0) if enabled is not None else None,
                        timeout_seconds,
                        (1 if require_confirmation else 0) if require_confirmation is not None else None,
                        now,
                    ),
                )
    finally:
        conn.close()


def get_skill_overrides(db_path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Retrieve all persistent skill overrides."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM skill_overrides;")
        rows = cur.fetchall()
        res = {}
        for r in rows:
            res[r["skill_id"]] = {
                "enabled": bool(r["enabled"]) if r["enabled"] is not None else None,
                "timeout_seconds": r["timeout_seconds"],
                "require_confirmation": bool(r["require_confirmation"]) if r["require_confirmation"] is not None else None,
                "updated_at": r["updated_at"],
            }
        return res
    finally:
        conn.close()


# ── Task Persistence ──────────────────────────────────────────────────────────

def save_task_record(
    task_id: str,
    task_type: str,
    status: str = "pending",
    params: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create a new async task record."""
    now = _get_utc_now_iso()
    params_json = json.dumps(params or {}, ensure_ascii=False)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO task_records (task_id, task_type, status, progress, status_message, params_json, created_at)
                VALUES (?, ?, ?, 0.0, 'Task initialized', ?, ?);
                """,
                (task_id, task_type, status, params_json, now),
            )
    finally:
        conn.close()

    return {
        "task_id": task_id,
        "task_type": task_type,
        "status": status,
        "progress": 0.0,
        "status_message": "Task initialized",
        "created_at": now,
        "params": params or {},
    }


def update_task_record(
    task_id: str,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    status_message: Optional[str] = None,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update task progress, status, or completion outcome."""
    conn = get_connection(db_path)
    try:
        updates = []
        vals = []
        if status is not None:
            updates.append("status = ?")
            vals.append(status)
        if progress is not None:
            updates.append("progress = ?")
            vals.append(progress)
        if status_message is not None:
            updates.append("status_message = ?")
            vals.append(status_message)
        if result is not None:
            updates.append("result_json = ?")
            vals.append(json.dumps(result, ensure_ascii=False))
        if error is not None:
            updates.append("error = ?")
            vals.append(error)
        if started_at is not None:
            updates.append("started_at = ?")
            vals.append(started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            vals.append(completed_at)
        if elapsed_ms is not None:
            updates.append("elapsed_ms = ?")
            vals.append(elapsed_ms)

        if not updates:
            return True

        vals.append(task_id)
        with conn:
            cur = conn.execute(
                f"UPDATE task_records SET {', '.join(updates)} WHERE task_id = ?;",
                tuple(vals),
            )
            return cur.rowcount > 0
    finally:
        conn.close()


def get_task_record(task_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Fetch task details by task_id."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM task_records WHERE task_id = ?;", (task_id,))
        row = cur.fetchone()
        if not row:
            return None
        params = json.loads(row["params_json"]) if row["params_json"] else {}
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return {
            "task_id": row["task_id"],
            "task_type": row["task_type"],
            "status": row["status"],
            "progress": row["progress"],
            "status_message": row["status_message"],
            "params": params,
            "result": result,
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "elapsed_ms": row["elapsed_ms"],
        }
    finally:
        conn.close()


def list_task_records(
    status: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """List recent tasks optionally filtered by status."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM task_records WHERE status = ? ORDER BY created_at DESC LIMIT ?;",
                (status, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM task_records ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            )
        rows = cur.fetchall()
        tasks = []
        for r in rows:
            tasks.append({
                "task_id": r["task_id"],
                "task_type": r["task_type"],
                "status": r["status"],
                "progress": r["progress"],
                "status_message": r["status_message"],
                "params": json.loads(r["params_json"]) if r["params_json"] else {},
                "result": json.loads(r["result_json"]) if r["result_json"] else None,
                "error": r["error"],
                "created_at": r["created_at"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "elapsed_ms": r["elapsed_ms"],
            })
        return tasks
    finally:
        conn.close()


# ==============================================================================
# LLM Providers & Model Roles Persistence
# ==============================================================================

def list_providers(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """List all configured LLM providers."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM llm_providers ORDER BY created_at ASC;")
        rows = cur.fetchall()
        providers = []
        for r in rows:
            providers.append({
                "provider_id": r["provider_id"],
                "name": r["name"],
                "base_url": r["base_url"],
                "api_key": r["api_key"] or "",
                "enabled": bool(r["enabled"]),
                "models": json.loads(r["models_json"]) if r["models_json"] else [],
                "custom_headers": json.loads(r["custom_headers_json"]) if r["custom_headers_json"] else {},
                "timeout_seconds": r["timeout_seconds"] or 60,
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            })
        return providers
    finally:
        conn.close()


def get_provider_by_id(provider_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve single provider by provider_id."""
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM llm_providers WHERE provider_id = ?;", (provider_id,))
        r = cur.fetchone()
        if not r:
            return None
        return {
            "provider_id": r["provider_id"],
            "name": r["name"],
            "base_url": r["base_url"],
            "api_key": r["api_key"] or "",
            "enabled": bool(r["enabled"]),
            "models": json.loads(r["models_json"]) if r["models_json"] else [],
            "custom_headers": json.loads(r["custom_headers_json"]) if r["custom_headers_json"] else {},
            "timeout_seconds": r["timeout_seconds"] or 60,
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    finally:
        conn.close()


def save_provider(data: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Insert or update a provider."""
    conn = get_connection(db_path)
    now_iso = _get_utc_now_iso()
    pid = data.get("provider_id") or f"prov_{uuid.uuid4().hex[:8]}"
    name = data.get("name", "自定义供应商")
    base_url = data.get("base_url", "").strip().rstrip("/")
    enabled = 1 if data.get("enabled", True) else 0
    models = data.get("models", [])
    custom_headers = data.get("custom_headers", {})
    timeout_seconds = int(data.get("timeout_seconds", 60))

    models_json = json.dumps(models, ensure_ascii=False)
    headers_json = json.dumps(custom_headers, ensure_ascii=False)

    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT created_at, api_key FROM llm_providers WHERE provider_id = ?;", (pid,))
            existing = cur.fetchone()
            created_at = existing["created_at"] if existing else now_iso
            requested_key = data.get("api_key")
            if data.get("clear_api_key"):
                api_key = ""
            elif requested_key is None or str(requested_key).strip() == "":
                api_key = existing["api_key"] if existing else ""
            else:
                api_key = str(requested_key).strip()

            conn.execute("""
                INSERT INTO llm_providers (
                    provider_id, name, base_url, api_key, enabled,
                    models_json, custom_headers_json, timeout_seconds,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    name = excluded.name,
                    base_url = excluded.base_url,
                    api_key = excluded.api_key,
                    enabled = excluded.enabled,
                    models_json = excluded.models_json,
                    custom_headers_json = excluded.custom_headers_json,
                    timeout_seconds = excluded.timeout_seconds,
                    updated_at = excluded.updated_at;
            """, (
                pid, name, base_url, api_key, enabled,
                models_json, headers_json, timeout_seconds,
                created_at, now_iso
            ))
        return get_provider_by_id(pid, db_path=db_path) or {}
    finally:
        conn.close()


def delete_provider(provider_id: str, db_path: Optional[Path] = None) -> bool:
    """Delete a provider by provider_id."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM llm_providers WHERE provider_id = ?;", (provider_id,))
            conn.execute("DELETE FROM llm_model_roles WHERE provider_id = ?;", (provider_id,))
        return True
    finally:
        conn.close()


def get_model_roles(db_path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """
    Get configured model roles mapping.
    Default roles:
      - chat: 默认助手 / Chat模型
      - summary: 快速 / 标题概要模型
      - quant: 算法量化模型
      - debate: 深度推理 / 多空辩论模型
      - vision: 多模态 / 图表视觉模型
    """
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT role_key, provider_id, model_id FROM llm_model_roles;")
        rows = cur.fetchall()
        roles: Dict[str, Dict[str, str]] = {}
        for r in rows:
            roles[r["role_key"]] = {
                "provider_id": r["provider_id"],
                "model_id": r["model_id"],
            }
        return roles
    finally:
        conn.close()


def save_model_roles(roles_dict: Dict[str, Dict[str, str]], db_path: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    """Save or update model roles mapping."""
    conn = get_connection(db_path)
    now_iso = _get_utc_now_iso()
    try:
        with conn:
            for role_key, val in roles_dict.items():
                pid = val.get("provider_id", "")
                mid = val.get("model_id", "")
                conn.execute("""
                    INSERT INTO llm_model_roles (role_key, provider_id, model_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(role_key) DO UPDATE SET
                        provider_id = excluded.provider_id,
                        model_id = excluded.model_id,
                        updated_at = excluded.updated_at;
                """, (role_key, pid, mid, now_iso))
        return get_model_roles(db_path=db_path)
    finally:
        conn.close()

