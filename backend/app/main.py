"""Interest Calculator API.

Two upstreams, deliberately independent:

* ``/api/chat``            -> LiteLLM gateway -> the agent on AgentCore
* ``/api/calc``, ``/api/rates`` -> the MCP tool server, no LLM in the path

Neither depends on the other, so the calculators keep working when the model is
throttled or the gateway is down, and the chat keeps working if a tool is
temporarily unavailable.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .mcp_client import list_tools
from .routers import calc, chat, rates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0", description=__doc__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(rates.router)
app.include_router(calc.router)
app.include_router(chat.router)


@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    """Liveness plus enough detail to diagnose a misconfigured deployment."""
    tools: list[str] = []
    tools_error: str | None = None
    if settings.tools_configured:
        try:
            tools = await list_tools()
        except Exception as exc:                      # noqa: BLE001
            # Report it rather than failing the probe: the chat path may still
            # be fine, and the message is what tells you which half is broken.
            tools_error = str(exc)

    return {
        "status": "ok",
        "agent_configured": settings.agent_configured,
        "gateway": settings.litellm_base_url,
        "model": settings.agent_model,
        "tools_configured": settings.tools_configured,
        "tools": tools,
        "tools_error": tools_error,
    }
