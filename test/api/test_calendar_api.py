from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.calendar import calendar_api


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *_):
        return self

    def first(self):
        return self.row


class FakeDb:
    def __init__(self, row=None):
        self.row = row

    def query(self, *_):
        return FakeQuery(self.row)


def create_client(*, db=None):
    app = FastAPI()
    app.include_router(calendar_api.router, prefix="/api/v1")
    app.dependency_overrides[calendar_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[calendar_api.get_db] = lambda: db or FakeDb()
    return TestClient(app)


def test_calendar_status_api_reports_connection():
    disconnected = create_client().get("/api/v1/calendar/google/status")
    connected = create_client(db=FakeDb(SimpleNamespace(calendar_id="primary"))).get("/api/v1/calendar/google/status")

    assert disconnected.status_code == 200
    assert disconnected.json() == {"connected": False, "calendar_id": None}
    assert connected.status_code == 200
    assert connected.json() == {"connected": True, "calendar_id": "primary"}


def test_calendar_events_api_filters_to_user_bobbeori_keys(monkeypatch):
    class FakeGoogleResponse:
        status_code = 200

        def json(self):
            return {
                "items": [
                    {
                        "id": "event-1",
                        "summary": "expiry",
                        "colorId": "11",
                        "htmlLink": "https://calendar/event-1",
                        "start": {"date": "2026-07-07"},
                        "extendedProperties": {"private": {"bobbeoriKey": "ingredient-expiry-7-2026-07-07"}},
                    },
                    {
                        "id": "event-2",
                        "summary": "other user",
                        "start": {"date": "2026-07-07"},
                        "extendedProperties": {"private": {"bobbeoriKey": "ingredient-expiry-8-2026-07-07"}},
                    },
                    {"id": "event-3", "summary": "plain", "start": {"date": "2026-07-07"}},
                    {
                        "id": "event-4",
                        "summary": "cancelled",
                        "status": "cancelled",
                        "start": {"date": "2026-07-07"},
                        "extendedProperties": {"private": {"bobbeoriKey": "ingredient-expiry-7-2026-07-07"}},
                    },
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, *_, **__):
            return FakeGoogleResponse()

    async def fake_access_token(*_):
        return "token"

    monkeypatch.setattr(calendar_api, "_get_google_integration", lambda db, user_id: SimpleNamespace(calendar_id="primary"))
    monkeypatch.setattr(calendar_api, "_get_access_token", fake_access_token)
    monkeypatch.setattr(calendar_api.httpx, "AsyncClient", FakeAsyncClient)

    response = create_client().get("/api/v1/calendar/google/events?start_date=2026-07-07&end_date=2026-07-08")

    assert response.status_code == 200
    assert response.json()["events"] == [
        {
            "id": "event-1",
            "dateKey": "2026-07-07",
            "title": "expiry",
            "colorId": "11",
            "htmlLink": "https://calendar/event-1",
            "eventKey": "ingredient-expiry-7-2026-07-07",
        }
    ]


def test_calendar_delete_api_blocks_other_users_event_key():
    response = create_client().delete("/api/v1/calendar/google/events/ingredient-expiry-8-2026-07-07")

    assert response.status_code == 403
