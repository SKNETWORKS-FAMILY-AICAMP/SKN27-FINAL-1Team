from .shopping_utils import (
    SHOPPING_CONFIRM_ACTIONS,
    analyze_shopping_intent,
    build_shopping_response,
    to_supervisor_state,
)

__all__ = [
    "SHOPPING_CONFIRM_ACTIONS",
    "analyze_shopping_intent",
    "build_shopping_response",
    "execute_shopping_action",
    "run_shopping_agent",
    "to_supervisor_state",
]


def __getattr__(name: str):
    if name in {"execute_shopping_action", "run_shopping_agent"}:
        from .shopping_agent import execute_shopping_action, run_shopping_agent

        return {
            "execute_shopping_action": execute_shopping_action,
            "run_shopping_agent": run_shopping_agent,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
