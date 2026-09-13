# -*- coding: utf-8 -*-
"""
server.api.sessions - Session lifecycle and message history endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from server.db import (
    create_session,
    delete_session,
    get_messages,
    get_session,
    get_session_memories,
    list_sessions,
    update_session_title,
)
from server.models import (
    MessageItem,
    SessionCreateRequest,
    SessionDetailResponse,
    SessionListResponse,
    SessionMemoryItem,
    SessionResponse,
    SessionTitleUpdateRequest,
)

router = APIRouter(prefix="/api/chat/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse)
async def api_create_session(req: SessionCreateRequest) -> SessionResponse:
    """Create a new chat session."""
    sid = req.session_id or (req.meta.get("session_id") if req.meta else None)
    sess = create_session(title=req.title, model=req.model, meta=req.meta, session_id=sid)
    return SessionResponse(**sess)



@router.get("", response_model=SessionListResponse)
async def api_list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    """Retrieve chat sessions list ordered by recent activity."""
    rows = list_sessions(limit=limit, offset=offset)
    sessions = [SessionResponse(**r) for r in rows]
    return SessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def api_get_session(session_id: str) -> SessionDetailResponse:
    """Get session metadata, full message history, and structured session memories."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    raw_msgs = get_messages(session_id, limit=200)
    messages = [MessageItem(**m) for m in raw_msgs]
    raw_memories = get_session_memories(session_id, limit=100)
    memories = [SessionMemoryItem(**mem) for mem in raw_memories]
    return SessionDetailResponse(
        session=SessionResponse(**sess),
        messages=messages,
        memories=memories,
    )


@router.put("/{session_id}/title", response_model=SessionResponse)
async def api_update_session_title(session_id: str, req: SessionTitleUpdateRequest) -> SessionResponse:
    """Update title of a chat session."""
    sess = get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    success = update_session_title(session_id, req.title)
    if not success:
        raise HTTPException(status_code=500, detail="更新会话标题失败")
    updated_sess = get_session(session_id)
    return SessionResponse(**updated_sess)


@router.delete("/{session_id}")
async def api_delete_session(session_id: str):
    """Delete a session and its associated chat history."""
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话不存在或已删除: {session_id}")
    return {"status": "deleted", "session_id": session_id}
