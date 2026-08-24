"""Rate lookup endpoints, served over MCP. No LLM involved."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..mcp_client import ToolError, call_tool

router = APIRouter(prefix="/api/rates", tags=["rates"])


def _status_for(exc: ToolError) -> int:
    return 503 if "could not reach" in str(exc) or "not set" in str(exc) else 422


@router.get("/catalog")
async def catalog() -> dict:
    try:
        result = await call_tool("list_available_rates", {})
    except ToolError as exc:
        raise HTTPException(_status_for(exc), str(exc)) from exc
    return {"rates": result.get("detail", {}).get("rates", [])}


@router.get("/board")
async def board() -> dict:
    """Headline rates, reshaped to the flat list the frontend already expects."""
    try:
        result = await call_tool("get_rate_board", {})
    except ToolError as exc:
        raise HTTPException(_status_for(exc), str(exc)) from exc
    return {"rates": result.get("detail", {}).get("rates", [])}


@router.get("/{rate_key}/history")
async def history(
    rate_key: str,
    months: int = Query(24, ge=1, le=600, description="Months of history"),
) -> dict:
    try:
        return await call_tool("get_rate_history",
                               {"rate_key": rate_key, "months": months})
    except ToolError as exc:
        raise HTTPException(_status_for(exc), str(exc)) from exc


@router.get("/{rate_key}")
async def single(rate_key: str) -> dict:
    try:
        result = await call_tool("get_current_rate", {"rate_key": rate_key})
    except ToolError as exc:
        raise HTTPException(_status_for(exc), str(exc)) from exc
    return result.get("detail", result)
