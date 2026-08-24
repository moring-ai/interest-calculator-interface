"""Deterministic calculator endpoints, served over MCP.

These call the same tools the agent calls, on the same server, so the two paths
cannot produce different numbers. No LLM is involved: the arithmetic is
deterministic, and this route stays fast and available even when the model or
the gateway is not.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..mcp_client import ToolError, call_tool

router = APIRouter(prefix="/api/calc", tags=["calculators"])


class MortgageRequest(BaseModel):
    loan_amount: float | None = Field(None, gt=0)
    annual_rate_percent: float | None = Field(None, ge=0, le=50)
    term_years: int = Field(30, ge=1, le=50)
    home_price: float | None = Field(None, gt=0)
    down_payment: float | None = Field(None, ge=0)
    extra_monthly_payment: float = Field(0, ge=0)
    extra_annual_payment: float = Field(0, ge=0)


class MortgageOption(BaseModel):
    label: str | None = None
    loan_amount: float = Field(..., gt=0)
    annual_rate_percent: float | None = Field(None, ge=0, le=50)
    term_years: int = Field(30, ge=1, le=50)
    extra_monthly_payment: float = Field(0, ge=0)


class CompareRequest(BaseModel):
    options: list[MortgageOption] = Field(..., min_length=2, max_length=4)


class SavingsRequest(BaseModel):
    initial_deposit: float = Field(0, ge=0)
    apy_percent: float | None = Field(None, ge=0, le=50)
    years: float = Field(10, gt=0, le=100)
    monthly_contribution: float = Field(0, ge=0)
    annual_contribution_growth_percent: float = Field(0, ge=0, le=100)
    inflation_rate_percent: float | None = Field(None, ge=-10, le=50)
    adjust_for_inflation: bool = True


class CapitalGainsRequest(BaseModel):
    sale_proceeds: float = Field(..., ge=0)
    cost_basis: float = Field(..., ge=0)
    holding_period_days: int | None = Field(None, ge=0)
    is_long_term: bool | None = None
    other_taxable_income: float = Field(0, ge=0)
    filing_status: Literal[
        "single", "married_jointly", "married_separately", "head_of_household"
    ] = "single"
    state_tax_rate_percent: float = Field(0, ge=0, le=20)


async def _call(tool: str, arguments: dict) -> dict:
    try:
        return await call_tool(tool, arguments)
    except ToolError as exc:
        # 422 for an argument the tool rejected, 503 when the server is
        # unreachable -- the client can retry the second but not the first.
        status = 503 if "could not reach" in str(exc) or "not set" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc


@router.post("/mortgage")
async def mortgage(req: MortgageRequest) -> dict:
    return await _call("calculate_mortgage", req.model_dump(exclude_none=True))


@router.post("/mortgage/compare")
async def compare(req: CompareRequest) -> dict:
    return await _call("compare_mortgage_options",
                       {"options": [o.model_dump(exclude_none=True) for o in req.options]})


@router.post("/savings")
async def savings(req: SavingsRequest) -> dict:
    return await _call("calculate_savings", req.model_dump(exclude_none=True))


@router.post("/capital-gains")
async def capital_gains(req: CapitalGainsRequest) -> dict:
    return await _call("calculate_capital_gains", req.model_dump(exclude_none=True))
