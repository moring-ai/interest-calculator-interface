"""Chat endpoint: one conversational turn, proxied through LiteLLM."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent_client import stream_turn
from ..config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    #: Reusing a session id keeps the agent's conversation history.
    session_id: str | None = None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("/status")
async def status() -> dict:
    s = get_settings()
    return {
        "agent_configured": s.agent_configured,
        "gateway": s.litellm_base_url,
        "model": s.agent_model,
    }


@router.post("")
async def chat(req: ChatRequest) -> StreamingResponse:
    settings = get_settings()
    if not settings.agent_configured:
        raise HTTPException(
            503,
            "No LiteLLM gateway is configured. Set LITELLM_BASE_URL and "
            "AGENT_MODEL, or use /api/calc, which needs no agent.",
        )

    # AgentCore requires a session id of at least 33 characters.
    session_id = req.session_id or uuid.uuid4().hex + uuid.uuid4().hex[:8]

    async def generate():
        yield _sse({"type": "session", "session_id": session_id})
        try:
            async for event in stream_turn(req.message, session_id):
                yield _sse(event)
        except Exception as exc:                      # noqa: BLE001
            log.exception("chat stream failed")
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
