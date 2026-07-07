from datetime import date

import pytest

from app.backend.api.calendar.calendar_api import (
    _bobbeori_event_key,
    _daily_event_keys,
    _event_key_belongs_to_user,
    _event_target_date,
)
from app.backend.services.calendar_mcp_client import _serverless_output


@pytest.mark.parametrize(
    "event_key",
    [
        "ingredient-expiry-7-2026-07-07",
        "today-menu-7-2026-07-07",
        "recipe-delete-7-2026-07-07",
        "receipt-cost-7-42",
        "calendar-agent-7-2026-07-07T09:00:00+09:00-abcd",
    ],
)
def test_calendar_feature_accepts_current_user_event_key_prefixes(event_key):
    assert _event_key_belongs_to_user(event_key, 7)


@pytest.mark.parametrize(
    "event_key",
    [
        "ingredient-expiry-8-2026-07-07",
        "today-menu-17-2026-07-07",
        "recipe-delete-70-2026-07-07",
        "receipt-cost-1-42",
        "calendar-agent-7",
        "personal-event-7-42",
    ],
)
def test_calendar_feature_rejects_foreign_or_unknown_event_keys(event_key):
    assert not _event_key_belongs_to_user(event_key, 7)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "COMPLETED", "output": {"event_id": "ok"}}, {"event_id": "ok"}),
        ({"status": "COMPLETED", "output": {"deleted": True}}, {"deleted": True}),
        ({"status": "COMPLETED", "output": []}, None),
        ({"status": "IN_QUEUE", "output": {"event_id": "pending"}}, None),
        ({"status": "FAILED", "output": {"event_id": "failed"}}, None),
    ],
)
def test_calendar_mcp_feature_serverless_output_matrix(payload, expected):
    assert _serverless_output(payload) == expected


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"extendedProperties": {"private": {"bobbeoriKey": "receipt-cost-7-42"}}}, "receipt-cost-7-42"),
        ({"extendedProperties": {"private": {"bobbeoriKey": 123}}}, None),
        ({"extendedProperties": {"private": {}}}, None),
        ({"extendedProperties": {}}, None),
        ({}, None),
    ],
)
def test_calendar_feature_reads_bobbeori_key_only_when_string(item, expected):
    assert _bobbeori_event_key(item) == expected


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"start": {"date": "2026-07-07"}}, date(2026, 7, 7)),
        ({"start": {"dateTime": "2026-07-08T07:00:00+09:00"}}, date(2026, 7, 8)),
        ({"start": {"dateTime": "2026-12-31T23:59:00+09:00"}}, date(2026, 12, 31)),
        ({"start": {}}, None),
    ],
)
def test_calendar_feature_extracts_event_target_date(event, expected):
    assert _event_target_date(event) == expected


@pytest.mark.parametrize("target_date", [date(2026, 7, 7), date(2026, 12, 31), date(2027, 1, 1)])
def test_calendar_feature_daily_event_keys_are_date_scoped(target_date):
    keys = _daily_event_keys(7, target_date)

    assert len(keys) == 3
    assert all(key.endswith(f"7-{target_date.isoformat()}") for key in keys)
