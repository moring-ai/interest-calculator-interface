"""MCP client for the deterministic calculators.

The backend calls the same MCP server the agent uses, rather than importing the
finance packages. That is what keeps a single source of truth after the split:
the math lives in the agent repository and is deployed once, and both callers
reach it the same way, so a chat answer and a calculator response cannot
disagree about a number.

No LLM is involved on this path. It exists because the arithmetic is
deterministic -- paying for a model round trip to reach it would add latency and
a failure mode for nothing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .config import get_settings

log = logging.getLogger(__name__)

#: Environment variables naming a CA bundle, in the order they are consulted.
#: httpx trusts certifi's bundle and ignores these, which breaks on any network
#: that terminates TLS -- a corporate proxy or a ZTNA agent. The MCP endpoint is
#: HTTPS, so without this the tool server is simply unreachable and the API
#: reports an opaque "unhandled errors in a TaskGroup".
CA_BUNDLE_VARS = ("MCP_CA_BUNDLE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


def resolve_ca_bundle() -> str | bool:
    for var in CA_BUNDLE_VARS:
        path = os.environ.get(var, "").strip()
        if path and os.path.isfile(path):
            return path
    return True


def _http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Build the httpx client the MCP transport uses, with our trust settings.

    Matches the signature of `mcp.shared._httpx_utils.create_mcp_http_client`,
    which is what `streamablehttp_client` expects.
    """
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout if timeout is not None else httpx.Timeout(30.0),
        auth=auth,
        verify=resolve_ca_bundle(),
        follow_redirects=True,
    )


class ToolError(RuntimeError):
    """The tool server rejected the call or could not be reached."""


def _unwrap(result: Any) -> dict:
    """Get the tool's envelope out of an MCP CallToolResult."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP wraps a bare dict return under "result" when it cannot infer
        # a richer output schema; unwrap that so callers see the envelope.
        if set(structured.keys()) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured

    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise ToolError("tool returned no readable content")


async def call_tool(name: str, arguments: dict | None = None) -> dict:
    """Call one MCP tool and return its envelope.

    A fresh session per call: the server runs in stateless HTTP mode, so there
    is no session state worth preserving, and a per-request session avoids
    having to keep an anyio task group alive across FastAPI's request lifecycle.
    """
    settings = get_settings()
    if not settings.tools_configured:
        raise ToolError(
            "MCP_SERVER_URL is not set, so the calculators have no tool server "
            "to call."
        )

    headers = (
        {"Authorization": f"Bearer {settings.mcp_server_token}"}
        if settings.mcp_server_token else None
    )

    try:
        async with streamablehttp_client(
            settings.mcp_server_url,
            headers=headers,
            timeout=settings.mcp_timeout_seconds,
            sse_read_timeout=settings.mcp_timeout_seconds,
            httpx_client_factory=_http_client_factory,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})
    except ToolError:
        raise
    except Exception as exc:                          # noqa: BLE001
        # anyio collapses transport failures into "unhandled errors in a
        # TaskGroup", which says nothing useful. Dig out the first real cause.
        detail = str(exc)
        inner = getattr(exc, "exceptions", None)
        if inner:
            detail = f"{type(inner[0]).__name__}: {inner[0]}"
        log.error("MCP call %s failed: %s", name, detail)
        raise ToolError(f"could not reach the tool server: {detail}") from exc

    if getattr(result, "isError", False):
        message = ""
        for block in getattr(result, "content", None) or []:
            message = getattr(block, "text", "") or message
        raise ToolError(message or f"tool {name} reported an error")

    return _unwrap(result)


async def list_tools() -> list[str]:
    """Names of the tools the server currently exposes. Used by /api/health."""
    settings = get_settings()
    if not settings.tools_configured:
        return []
    headers = (
        {"Authorization": f"Bearer {settings.mcp_server_token}"}
        if settings.mcp_server_token else None
    )
    async with streamablehttp_client(
        settings.mcp_server_url, headers=headers,
        timeout=settings.mcp_timeout_seconds,
        httpx_client_factory=_http_client_factory,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return [t.name for t in (await session.list_tools()).tools]
