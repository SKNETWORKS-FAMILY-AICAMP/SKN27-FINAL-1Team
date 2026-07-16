from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .recipe_config import WHEN_ALWAYS


@dataclass(frozen=True)
class PlanStep:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    when: str = WHEN_ALWAYS


@dataclass
class RecipePlan:
    steps: list[PlanStep]
    max_fallback: int = 1


@dataclass
class RecipeAgentRequest:
    text: str
    db: Any
    user_id: int | None
    history: list
    settings_obj: Any
    intent: str


@dataclass
class RecipeAgentResult:
    ok: bool
    agent: str
    intent: str
    message: str
    error: dict[str, Any] | None
    actions: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    meta: dict[str, Any]


@dataclass
class RecipeExecutionState:
    """Agent loop internal state."""
    req: RecipeAgentRequest
    plan: RecipePlan | None = None
    steps_done: list[str] = field(default_factory=list)
    intermediate: dict[str, Any] = field(default_factory=dict)
    last_tool: str | None = None
