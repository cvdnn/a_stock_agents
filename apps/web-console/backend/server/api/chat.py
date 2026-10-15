# -*- coding: utf-8 -*-
"""
server.api.chat - AIChat completions SSE streaming endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from server.agent.react_runner import AgentReActRunner
from server.models import ChatMessageRequest

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/completions/stream")
async def chat_completions_stream(req: ChatMessageRequest):
    """
    Stream chat response and tool execution via Server-Sent Events (SSE).
    """
    runner = AgentReActRunner()
    generator = runner.run_chat_stream(
        message=req.message,
        session_id=req.session_id,
        model=req.model,
        tools_enabled=req.tools_enabled,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
