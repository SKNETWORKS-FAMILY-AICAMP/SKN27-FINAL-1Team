import asyncio
from datetime import date
from unittest.mock import AsyncMock

from app.backend.api.calendar.calendar_api import _alert_time, _daily_event_keys, _event_target_date
from app.backend.services import calendar_mcp_client


def test_calendar_feature_daily_sync_keys_cover_three_bobbeori_alarm_types():
    keys = _daily_event_keys(7, date(2026, 7, 7))

    assert keys == {
        "ingredient-expiry-7-2026-07-07",
        "today-menu-7-2026-07-07",
        "recipe-delete-7-2026-07-07",
    }


def test_calendar_feature_alert_time_uses_kst_ten_minute_window_and_popup():
    start, end, reminders = _alert_time(date(2026, 7, 7), 7, 0)

    assert start == {"dateTime": "2026-07-07T07:00:00+09:00"}
    assert end == {"dateTime": "2026-07-07T07:10:00+09:00"}
    assert reminders == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]}


def test_calendar_feature_target_date_reads_all_day_and_timed_google_events():
    assert _event_target_date({"start": {"date": "2026-07-07"}}) == date(2026, 7, 7)
    assert _event_target_date({"start": {"dateTime": "2026-07-08T07:00:00+09:00"}}) == date(2026, 7, 8)


def test_calendar_mcp_feature_runsync_url_adds_endpoint_once(monkeypatch):
    monkeypatch.setattr(calendar_mcp_client.settings, "RUNPOD_CALENDAR_SERVERLESS_URL", "https://api.runpod.ai/v2/abc")
    assert calendar_mcp_client._runsync_url() == "https://api.runpod.ai/v2/abc/runsync"

    monkeypatch.setattr(calendar_mcp_client.settings, "RUNPOD_CALENDAR_SERVERLESS_URL", "https://api.runpod.ai/v2/abc/runsync")
    assert calendar_mcp_client._runsync_url() == "https://api.runpod.ai/v2/abc/runsync"


def test_calendar_mcp_feature_no_serverless_url_skips_tool_call(monkeypatch):
    monkeypatch.setattr(calendar_mcp_client.settings, "RUNPOD_CALENDAR_SERVERLESS_URL", "")

    result = asyncio.run(calendar_mcp_client._call_calendar_tool("create_calendar_event", {}))

    assert result is None


def test_calendar_mcp_feature_create_and_delete_filter_tool_outputs(monkeypatch):
    call_tool = AsyncMock(
        side_effect=[
            {"event_id": "google-event"},
            {"deleted": True},
            {"ignored": True},
        ]
    )
    monkeypatch.setattr(calendar_mcp_client, "_call_calendar_tool", call_tool)

    created = asyncio.run(
        calendar_mcp_client.create_calendar_event_with_mcp(7, "primary", "token", "calendar-agent-7-x", {}, "manual")
    )
    deleted = asyncio.run(calendar_mcp_client.delete_calendar_event_with_mcp(7, "primary", "token", "calendar-agent-7-x"))
    ignored = asyncio.run(
        calendar_mcp_client.create_calendar_event_with_mcp(7, "primary", "token", "calendar-agent-7-x", {}, "manual")
    )

    assert created == {"event_id": "google-event"}
    assert deleted == {"deleted": True}
    assert ignored is None
