from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Stable response envelope shared by every Bobbeori MCP tool."""

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    next_actions: list[str] = Field(default_factory=list)
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex}")
