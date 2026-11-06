"""Schemas for the health-check endpoint."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    app_name: str
    version: str
    environment: str
    timestamp: datetime
