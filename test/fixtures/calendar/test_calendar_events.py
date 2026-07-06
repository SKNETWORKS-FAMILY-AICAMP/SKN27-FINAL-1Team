import os
import sys
import asyncio
import importlib
from datetime import date
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.api.calendar import calendar_api
from app.backend.api.calendar.calendar_api import (
    _bobbeori_event_key,
    _create_event_once,
    _daily_event_keys,
    _delete_event_once,
    _event_key_belongs_to_user,
    _sync_daily_events,
)
from app.backend.api.receipts.receipts_api import confirm_receipt_items
from app.backend.schemas.receipts import ReceiptConfirmItem, ReceiptConfirmRequest
from app.backend.services import calendar_mcp_client
from app.backend.services.calendar_mcp_client import (
    _call_calendar_tool,
    _serverless_output,
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

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text or f"HTTP {self.status_code}")


# httpx.AsyncClient 대신 쓰는 fake client. 네트워크 없이 lookup/post/patch/delete 호출을 기록한다.
class FakeCalendarClient:
    def __init__(self, *_, items=None, **__):
        self.items = items or []
        self.deleted_urls = []
        self.posted = []
        self.patched = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

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


def test_bobbeori_event_key_reads_private_extended_property():
    item = {"extendedProperties": {"private": {"bobbeoriKey": "today-menu-7-2026-06-29"}}}
    assert _bobbeori_event_key(item) == "today-menu-7-2026-06-29"
    assert _bobbeori_event_key({"extendedProperties": {"shared": {"bobbeoriKey": "x"}}}) is None


def test_list_google_calendar_events_only_returns_our_visible_events():
    client = FakeCalendarClient(
        items=[
            {
                "id": "ours",
                "summary": "Bobbeori event",
                "start": {"date": "2026-06-29"},
                "extendedProperties": {"private": {"bobbeoriKey": "today-menu-7-2026-06-29"}},
            },
            {"id": "personal", "summary": "Private event", "start": {"date": "2026-06-29"}},
            {
                "id": "other-user",
                "summary": "Other user event",
                "start": {"date": "2026-06-29"},
                "extendedProperties": {"private": {"bobbeoriKey": "today-menu-17-2026-06-29"}},
            },
            {
                "id": "cancelled",
                "status": "cancelled",
                "start": {"date": "2026-06-29"},
                "extendedProperties": {"private": {"bobbeoriKey": "today-menu-7-2026-06-29"}},
            },
        ]
    )

    with (
        patch.object(calendar_api, "_get_google_integration", return_value=SimpleNamespace(calendar_id="primary")),
        patch.object(calendar_api, "_get_access_token", new=AsyncMock(return_value="access-token")),
        patch.object(calendar_api.httpx, "AsyncClient", return_value=client),
    ):
        result = asyncio.run(
            calendar_api.list_google_calendar_events(
                date(2026, 6, 29),
                date(2026, 6, 30),
                current_user_id=7,
                db=MagicMock(),
            )
        )

    assert result["events"] == [
        {
            "id": "ours",
            "dateKey": "2026-06-29",
            "title": "Bobbeori event",
            "colorId": None,
            "htmlLink": None,
            "eventKey": "today-menu-7-2026-06-29",
        }
    ]


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


# RunPod serverless runsync 응답은 COMPLETED output만 성공으로 본다.
def test_serverless_output_reads_completed_output():
    assert _serverless_output({"status": "COMPLETED", "output": {"event_id": "serverless"}}) == {"event_id": "serverless"}
    assert _serverless_output({"status": "FAILED", "output": {"event_id": "serverless"}}) is None
    assert _serverless_output({"status": "COMPLETED", "output": "not json object"}) is None


def test_call_calendar_tool_posts_runpod_runsync_request():
    calls = []

    class FakeRunPodClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, url, **kwargs):
            calls.append((self.timeout, url, kwargs))
            return FakeResponse(payload={"status": "COMPLETED", "output": {"event_id": "runpod-event"}})

    with (
        patch.object(calendar_mcp_client.settings, "RUNPOD_CALENDAR_SERVERLESS_URL", "https://runpod.example/v2/abc"),
        patch.object(calendar_mcp_client.settings, "RUNPOD_API_KEY", "api-key"),
        patch.object(calendar_mcp_client.settings, "RUNPOD_INTERNAL_TOKEN", "internal-token"),
        patch.object(calendar_mcp_client.settings, "RUNPOD_TIMEOUT_SECONDS", 60),
        patch.object(calendar_mcp_client.httpx, "AsyncClient", FakeRunPodClient),
    ):
        result = asyncio.run(_call_calendar_tool("create_calendar_event", {"event_key": "today-menu-7-2026-06-29"}))

    assert result == {"event_id": "runpod-event"}
    timeout, url, kwargs = calls[0]
    assert timeout == 60
    assert url == "https://runpod.example/v2/abc/runsync"
    assert kwargs["headers"] == {
        "Authorization": "Bearer api-key",
        "X-Internal-Token": "internal-token",
    }
    assert kwargs["json"] == {
        "input": {
            "tool": "create_calendar_event",
            "arguments": {"event_key": "today-menu-7-2026-06-29"},
            "internal_token": "internal-token",
        }
    }


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


def test_runpod_handler_checks_token_and_dispatches_tool():
    started = []
    fake_runpod = ModuleType("runpod")
    fake_runpod.serverless = SimpleNamespace(start=lambda config: started.append(config))
    fake_server = ModuleType("ai.calendar.runpod_server")

    async def fake_create_calendar_event(**kwargs):
        return {"ok": True, "arguments": kwargs}

    async def fake_delete_calendar_event(**kwargs):
        return {"ok": True, "deleted": kwargs.get("event_key")}

    fake_server.create_calendar_event = fake_create_calendar_event
    fake_server.delete_calendar_event = fake_delete_calendar_event

    sys.modules.pop("ai.calendar.runpod_handler", None)
    with (
        patch.dict(sys.modules, {"runpod": fake_runpod, "ai.calendar.runpod_server": fake_server}),
        patch.dict(os.environ, {}, clear=True),
    ):
        handler_module = importlib.import_module("ai.calendar.runpod_handler")
        try:
            assert handler_module.handler({"input": {"internal_token": "secret"}}) == {
                "ok": False,
                "message": "RUNPOD_INTERNAL_TOKEN is not configured",
            }
        finally:
            sys.modules.pop("ai.calendar.runpod_handler", None)

    with (
        patch.dict(sys.modules, {"runpod": fake_runpod, "ai.calendar.runpod_server": fake_server}),
        patch.dict(os.environ, {"RUNPOD_INTERNAL_TOKEN": "secret"}),
    ):
        handler_module = importlib.import_module("ai.calendar.runpod_handler")
        try:
            assert started[-1]["handler"] is handler_module.handler
            assert handler_module.handler({"input": {"internal_token": "wrong"}}) == {
                "ok": False,
                "message": "invalid internal token",
            }
            assert handler_module.handler({"input": {"internal_token": "secret", "tool": "missing"}}) == {
                "ok": False,
                "message": "unknown tool",
            }
            assert handler_module.handler(
                {
                    "input": {
                        "internal_token": "secret",
                        "tool": "create_calendar_event",
                        "arguments": {"event_key": "receipt-cost-7-42"},
                    }
                }
            ) == {"ok": True, "arguments": {"event_key": "receipt-cost-7-42"}}
        finally:
            sys.modules.pop("ai.calendar.runpod_handler", None)


def test_runpod_mcp_server_updates_and_deletes_bobbeori_event():
    fake_mcp = ModuleType("mcp")
    fake_mcp_server = ModuleType("mcp.server")
    fake_fastmcp_module = ModuleType("mcp.server.fastmcp")
    fake_transport_module = ModuleType("mcp.server.transport_security")

    class FakeApp:
        def add_middleware(self, *_):
            pass

    class FakeFastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self):
            return lambda func: func

        def custom_route(self, *_args, **_kwargs):
            return lambda func: func

        def streamable_http_app(self):
            return FakeApp()

    class FakeTransportSecuritySettings:
        def __init__(self, **_kwargs):
            pass

    fake_fastmcp_module.FastMCP = FakeFastMCP
    fake_transport_module.TransportSecuritySettings = FakeTransportSecuritySettings

    sys.modules.pop("ai.calendar.runpod_server", None)
    with (
        patch.dict(
            sys.modules,
            {
                "mcp": fake_mcp,
                "mcp.server": fake_mcp_server,
                "mcp.server.fastmcp": fake_fastmcp_module,
                "mcp.server.transport_security": fake_transport_module,
            },
        ),
        patch.dict(os.environ, {"RUNPOD_INTERNAL_TOKEN": "secret"}),
    ):
        runpod_server = importlib.import_module("ai.calendar.runpod_server")

    try:
        update_client = FakeCalendarClient(items=[{"id": "google-event", "summary": "old"}])
        event = {
            "summary": "new",
            "description": " memo ",
            "start": {"date": "2026-06-29"},
            "end": {"date": "2026-06-29"},
        }
        with patch.object(runpod_server.httpx, "AsyncClient", return_value=update_client):
            updated = asyncio.run(
                runpod_server.create_calendar_event(
                    "access-token",
                    "receipt-cost-7-42",
                    event,
                    calendar_id="primary",
                    source="receipt",
                    user_id=7,
                )
            )

        assert updated["updated"] is True
        assert update_client.patched[0][0].endswith("/google-event")
        patched_event = update_client.patched[0][1]["json"]
        assert patched_event["description"] == "memo"
        assert patched_event["extendedProperties"]["private"]["bobbeoriKey"] == "receipt-cost-7-42"

        delete_client = FakeCalendarClient(items=[{"id": "google-event"}])
        with patch.object(runpod_server.httpx, "AsyncClient", return_value=delete_client):
            deleted = asyncio.run(runpod_server.delete_calendar_event("access-token", "receipt-cost-7-42"))

        assert deleted == {
            "event_key": "receipt-cost-7-42",
            "event_id": "google-event",
            "deleted": True,
            "missing": False,
        }
        assert delete_client.deleted_urls[0].endswith("/google-event")
    finally:
        sys.modules.pop("ai.calendar.runpod_server", None)
