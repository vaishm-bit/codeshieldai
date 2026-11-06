"""Schemas shared across the API."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Any | None = Field(default=None, description="Optional extra context")


class ErrorResponse(BaseModel):
    """Standard error envelope returned by every failing endpoint."""

    error: ErrorDetail
