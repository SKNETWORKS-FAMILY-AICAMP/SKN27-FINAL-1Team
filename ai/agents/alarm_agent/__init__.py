from .alarm_agent import AGENT_NAME, apply_human_choice, analyze_intent, arun, build_response, execute_tool, run

_TOOL_EXPORTS = {
    "ALARM_AGENT_TOOLS",
    "create_calendar_event_tool",
    "delete_calendar_event_tool",
    "list_calendar_events_tool",
    "sync_daily_events_tool",
}


def __getattr__(name):
    if name in _TOOL_EXPORTS:
        from . import tools

        return getattr(tools, name)
    raise AttributeError(name)

__all__ = [
    "AGENT_NAME",
    "ALARM_AGENT_TOOLS",
    "apply_human_choice",
    "analyze_intent",
    "arun",
    "build_response",
    "create_calendar_event_tool",
    "delete_calendar_event_tool",
    "execute_tool",
    "list_calendar_events_tool",
    "sync_daily_events_tool",
    "run",
]
