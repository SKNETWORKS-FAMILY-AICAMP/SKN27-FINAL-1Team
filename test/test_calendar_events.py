import os
import sys
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.api.calendar.calendar_api import (
    _create_event_once,
    _daily_event_keys,
    _delete_event_once,
    _event_key_belongs_to_user,
    _sync_daily_events,
)
from app.backend.api.receipts.receipts_api import confirm_receipt_items
from app.backend.schemas.receipts import ReceiptConfirmItem, ReceiptConfirmRequest
from app.backend.services.calendar_mcp_client import (
    _structured_result,
    create_calendar_event_with_mcp,
    delete_calendar_event_with_mcp,
)


# Google Calendar API 응답 흉내. 테스트에서 필요한 최소 필드만 둔다.
class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


# httpx.AsyncClient 대신 쓰는 fake client. 네트워크 없이 lookup/post/patch/delete 호출을 기록한다.
class FakeCalendarClient:
    def __init__(self, items=None):
        self.items = items or []
        self.deleted_urls = []
        self.posted = []
        self.patched = []

    async def get(self, *_, **__):
        return FakeResponse(payload={"items": self.items})

    async def delete(self, url, **__):
        self.deleted_urls.append(url)
        return FakeResponse(status_code=204)

    async def post(self, url, **kwargs):
        self.posted.append((url, kwargs))
        return FakeResponse(payload={"id": "new-google-event", "htmlLink": "https://calendar/event"})

    async def patch(self, url, **kwargs):
        self.patched.append((url, kwargs))
        return FakeResponse(payload={"id": "patched-google-event", "htmlLink": "https://calendar/patched"})


# receipts_api.confirm_receipt_items 안의 async with httpx.AsyncClient(...) 대체용.
class FakeAsyncClient:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


# 영수증 확정 요청을 테스트별 옵션만 바꿔 재사용한다.
def _receipt_request(*, enabled=True, item_amount=12000, purchase_datetime="2026-06-29 12:30"):
    return ReceiptConfirmRequest(
        receipt_id=42,
        purchase_datetime=purchase_datetime,
        calendar_cost_enabled=enabled,
        items=[
            ReceiptConfirmItem(
                raw_name="계란",
                normalized_name="계란",
                quantity=1,
                unit="개",
                item_amount=item_amount,
            )
        ],
    )


# 일일 동기화가 관리하는 event_key 범위가 늘거나 줄면 이 테스트가 알려준다.
def test_daily_event_keys_cover_all_daily_calendar_messages():
    assert _daily_event_keys(7, date(2026, 6, 29)) == {
        "ingredient-expiry-7-2026-06-29",
        "today-menu-7-2026-06-29",
        "recipe-delete-7-2026-06-29",
    }


# 삭제 API는 다른 사용자 일정이나 임의 prefix를 건드리면 안 된다.
def test_event_key_delete_guard_only_allows_our_user_keys():
    assert _event_key_belongs_to_user("ingredient-expiry-7-2026-06-29", 7)
    assert _event_key_belongs_to_user("receipt-cost-7-42", 7)
    assert not _event_key_belongs_to_user("receipt-cost-17-42", 7)
    assert not _event_key_belongs_to_user("evil-7-42", 7)


# MCP 삭제가 실패/미설정이어도 Google API fallback으로 우리가 만든 이벤트를 삭제한다.
def test_delete_event_once_deletes_event_found_by_bobbeori_key():
    client = FakeCalendarClient(items=[{"id": "google-event-1"}])

    with patch("app.backend.api.calendar.calendar_api.delete_calendar_event_with_mcp", new=AsyncMock(return_value=None)):
        result = asyncio.run(
            _delete_event_once(
                client,
                "primary",
                "access-token",
                "today-menu-7-2026-06-29",
                user_id=7,
            )
        )

    assert result == {
        "event_key": "today-menu-7-2026-06-29",
        "event_id": "google-event-1",
        "deleted": True,
        "missing": False,
    }
    assert client.deleted_urls == ["https://www.googleapis.com/calendar/v3/calendars/primary/events/google-event-1"]


# MCP 생성이 실패/미설정이고 기존 이벤트가 없으면 Google API fallback으로 새 이벤트를 만든다.
def test_create_event_once_fallback_posts_when_mcp_and_google_lookup_miss():
    client = FakeCalendarClient()
    event = {"summary": "저녁 추천: 김치찌개"}

    with patch("app.backend.api.calendar.calendar_api.create_calendar_event_with_mcp", new=AsyncMock(return_value=None)):
        result = asyncio.run(
            _create_event_once(
                client,
                "primary",
                "access-token",
                "today-menu-7-2026-06-29",
                event,
                user_id=7,
            )
        )

    assert result == {"event_id": "new-google-event", "html_link": "https://calendar/event", "duplicate": False}
    assert client.posted[0][0] == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    assert client.posted[0][1]["json"]["extendedProperties"]["private"]["bobbeoriKey"] == "today-menu-7-2026-06-29"


# 오늘 계산된 이벤트만 남기고, 빠진 일일 이벤트 key는 삭제 대상으로 보낸다.
def test_sync_daily_events_deletes_daily_keys_that_are_no_longer_generated():
    created = AsyncMock(return_value={"event_id": "created"})
    deleted = AsyncMock(return_value={"deleted": True})
    events = [
        (
            "today-menu-7-2026-06-29",
            {"summary": "저녁 추천: 김치찌개"},
        )
    ]

    with (
        patch("app.backend.api.calendar.calendar_api._build_daily_events", return_value=events),
        patch("app.backend.api.calendar.calendar_api._create_event_once", created),
        patch("app.backend.api.calendar.calendar_api._delete_event_once", deleted),
    ):
        synced, removed = asyncio.run(
            _sync_daily_events(
                SimpleNamespace(),
                SimpleNamespace(),
                7,
                "primary",
                "access-token",
                date(2026, 6, 29),
                "daily",
            )
        )

    assert synced == [{"event_id": "created"}]
    assert removed == [{"deleted": True}, {"deleted": True}]
    created.assert_awaited_once()
    assert {call.args[3] for call in deleted.await_args_list} == {
        "ingredient-expiry-7-2026-06-29",
        "recipe-delete-7-2026-06-29",
    }


# MCP SDK 응답은 structuredContent를 우선하고, 없으면 text JSON fallback을 읽는다.
def test_structured_result_reads_structured_content_or_json_text():
    assert _structured_result(SimpleNamespace(structuredContent={"event_id": "structured"})) == {"event_id": "structured"}

    result = SimpleNamespace(structuredContent=None, content=[SimpleNamespace(text='{"event_id": "text"}')])
    assert _structured_result(result) == {"event_id": "text"}

    broken = SimpleNamespace(structuredContent=None, content=[SimpleNamespace(text="not json")])
    assert _structured_result(broken) is None


# create wrapper가 MCP tool 이름과 인자를 바꿔 보내지 않는지 확인한다.
def test_mcp_create_wrapper_passes_tool_name_and_arguments():
    call_tool = AsyncMock(return_value={"event_id": "mcp-event"})
    event = {"summary": "저녁 추천: 김치찌개"}

    with patch("app.backend.services.calendar_mcp_client._call_calendar_tool", call_tool):
        result = asyncio.run(
            create_calendar_event_with_mcp(7, "primary", "access-token", "today-menu-7-2026-06-29", event, "daily")
        )

    assert result == {"event_id": "mcp-event"}
    tool_name, arguments = call_tool.await_args.args
    assert tool_name == "create_calendar_event"
    assert arguments == {
        "user_id": 7,
        "calendar_id": "primary",
        "access_token": "access-token",
        "event_key": "today-menu-7-2026-06-29",
        "source": "daily",
        "event": event,
    }


# delete wrapper는 이미 없어진 이벤트(missing=True)도 정상 처리로 본다.
def test_mcp_delete_wrapper_accepts_missing_result():
    call_tool = AsyncMock(return_value={"event_key": "today-menu-7-2026-06-29", "deleted": False, "missing": True})

    with patch("app.backend.services.calendar_mcp_client._call_calendar_tool", call_tool):
        result = asyncio.run(delete_calendar_event_with_mcp(7, "primary", "access-token", "today-menu-7-2026-06-29"))

    assert result == {"event_key": "today-menu-7-2026-06-29", "deleted": False, "missing": True}
    tool_name, arguments = call_tool.await_args.args
    assert tool_name == "delete_calendar_event"
    assert arguments["event_key"] == "today-menu-7-2026-06-29"


# 영수증 비용 기록 조건이 맞으면 receipt-cost 이벤트를 생성한다.
def test_receipt_confirm_creates_calendar_cost_event_when_enabled():
    created = AsyncMock(return_value={"event_id": "receipt-event"})
    deleted = AsyncMock()

    with (
        patch("app.backend.api.receipts.receipts_api.receipt_confirm_service.save_confirmed_items", return_value=1),
        patch("app.backend.api.receipts.receipts_api._get_google_integration", return_value=SimpleNamespace(calendar_id="primary")),
        patch("app.backend.api.receipts.receipts_api._get_access_token", new=AsyncMock(return_value="access-token")),
        patch("app.backend.api.receipts.receipts_api._create_event_once", created),
        patch("app.backend.api.receipts.receipts_api._delete_event_once", deleted),
        patch("app.backend.api.receipts.receipts_api.httpx.AsyncClient", FakeAsyncClient),
    ):
        result = asyncio.run(confirm_receipt_items(_receipt_request(), current_user_id=7, db=MagicMock()))

    assert result == {"message": "성공적으로 1개 품목을 저장했습니다."}
    created.assert_awaited_once()
    deleted.assert_not_awaited()
    assert created.await_args.args[3] == "receipt-cost-7-42"
    assert created.await_args.args[4]["summary"] == "식재료 사용비용 12,000원"


# 영수증 비용 기록을 끄면 기존 receipt-cost 이벤트를 정리한다.
def test_receipt_confirm_deletes_calendar_cost_event_when_disabled():
    created = AsyncMock()
    deleted = AsyncMock(return_value={"deleted": True})

    with (
        patch("app.backend.api.receipts.receipts_api.receipt_confirm_service.save_confirmed_items", return_value=1),
        patch("app.backend.api.receipts.receipts_api._get_google_integration", return_value=SimpleNamespace(calendar_id="primary")),
        patch("app.backend.api.receipts.receipts_api._get_access_token", new=AsyncMock(return_value="access-token")),
        patch("app.backend.api.receipts.receipts_api._create_event_once", created),
        patch("app.backend.api.receipts.receipts_api._delete_event_once", deleted),
        patch("app.backend.api.receipts.receipts_api.httpx.AsyncClient", FakeAsyncClient),
    ):
        result = asyncio.run(confirm_receipt_items(_receipt_request(enabled=False), current_user_id=7, db=MagicMock()))

    assert result == {"message": "성공적으로 1개 품목을 저장했습니다."}
    created.assert_not_awaited()
    deleted.assert_awaited_once()
    assert deleted.await_args.args[3] == "receipt-cost-7-42"
