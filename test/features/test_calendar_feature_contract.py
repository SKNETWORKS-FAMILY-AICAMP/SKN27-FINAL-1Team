from app.backend.api.calendar.calendar_api import _bobbeori_event_key, _event_key_belongs_to_user
from app.backend.services.calendar_mcp_client import _serverless_output


def test_calendar_feature_accepts_only_our_bobbeori_event_keys():
    assert _event_key_belongs_to_user("today-menu-7-2026-07-03", 7)
    assert _event_key_belongs_to_user("receipt-cost-7-42", 7)
    assert not _event_key_belongs_to_user("receipt-cost-17-42", 7)
    assert not _event_key_belongs_to_user("personal-event-7-42", 7)


def test_calendar_feature_reads_google_event_key_contract():
    item = {"extendedProperties": {"private": {"bobbeoriKey": "receipt-cost-7-42"}}}
    assert _bobbeori_event_key(item) == "receipt-cost-7-42"


def test_calendar_feature_ab_serverless_completed_vs_not_ready():
    assert _serverless_output({"status": "COMPLETED", "output": {"event_id": "ok"}}) == {"event_id": "ok"}
    assert _serverless_output({"status": "IN_QUEUE", "output": {"event_id": "pending"}}) is None
