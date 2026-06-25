import os
from copy import deepcopy
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


app = FastAPI(title="Bobbeori Calendar MCP Server")


@app.on_event("startup")
def require_internal_token() -> None:
    """내부 토큰 없이 Runpod MCP 서버가 떠서 외부 호출에 노출되는 것을 막는다."""
    if not os.getenv("RUNPOD_INTERNAL_TOKEN"):
        raise RuntimeError("RUNPOD_INTERNAL_TOKEN is required")


class CreateEventRequest(BaseModel):
    """백엔드가 MCP에 넘기는 Google Calendar 이벤트 생성 요청."""

    user_id: int | None = None
    calendar_id: str = "primary"
    access_token: str
    event_key: str
    source: str = "manual"
    event: dict[str, Any] = Field(default_factory=dict)


def _check_token(token: str | None) -> None:
    """백엔드가 보낸 X-Internal-Token이 Runpod 환경변수와 같은지 검증한다."""
    expected = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token")


def _event_type(event_key: str) -> str:
    if event_key.startswith("ingredient-expiry"):
        return "ingredient_expiry"
    if event_key.startswith("today-menu"):
        return "dinner_recommendation"
    if event_key.startswith("recipe-delete"):
        return "recipe_expiry"
    if event_key.startswith("receipt-cost"):
        return "receipt_cost"
    return "calendar"


def _prepare_event(payload: CreateEventRequest) -> dict[str, Any]:
    """Google Calendar에 저장할 이벤트에 밥벌이 중복키/유형 메타데이터를 붙인다."""
    event = deepcopy(payload.event)
    private_props = event.get("extendedProperties", {}).get("private", {})
    event.setdefault("description", "")
    event["description"] = event["description"].strip()
    event["extendedProperties"] = {
        "private": {
            **private_props,
            "bobbeoriKey": payload.event_key,
            "bobbeoriType": _event_type(payload.event_key),
            "bobbeoriSource": payload.source,
        }
    }
    return event


def _result(item: dict[str, Any], event: dict[str, Any], duplicate: bool, updated: bool = False) -> dict[str, Any]:
    """백엔드가 DB 로그를 남길 수 있도록 Google 이벤트 결과를 공통 형태로 정리한다."""
    return {
        "event_id": item.get("id"),
        "html_link": item.get("htmlLink"),
        "duplicate": duplicate,
        "updated": updated,
        "event": event,
    }


@app.get("/health")
def health() -> dict[str, str]:
    """Runpod 프록시/서버 상태 확인용 엔드포인트."""
    return {"status": "ok"}


@app.post("/calendar/create-event")
async def create_event(
    payload: CreateEventRequest,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """bobbeoriKey로 기존 이벤트를 찾고, 있으면 수정/중복 처리하고 없으면 새로 생성한다."""
    _check_token(x_internal_token)
    event = _prepare_event(payload)
    url = f"https://www.googleapis.com/calendar/v3/calendars/{payload.calendar_id}/events"
    headers = {"Authorization": f"Bearer {payload.access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        existing_res = await client.get(
            url,
            headers=headers,
            params={
                "privateExtendedProperty": f"bobbeoriKey={payload.event_key}",
                "singleEvents": "true",
                "maxResults": 1,
            },
        )
        if existing_res.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event lookup failed.")

        existing = existing_res.json().get("items", [])
        if existing:
            item = existing[0]
            watched = ("summary", "description", "start", "end", "colorId", "reminders", "extendedProperties")
            if any(item.get(field) != event.get(field) for field in watched):
                event_res = await client.patch(f"{url}/{item.get('id')}", headers=headers, json=event)
                if event_res.status_code >= 400:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event update failed.")
                return _result(event_res.json(), event, duplicate=True, updated=True)
            return _result(item, event, duplicate=True)

        event_res = await client.post(url, headers=headers, json=event)
        if event_res.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event creation failed.")
        return _result(event_res.json(), event, duplicate=False)
