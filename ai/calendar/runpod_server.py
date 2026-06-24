import os
from copy import deepcopy
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


app = FastAPI(title="Bobbeori Calendar MCP Server")


@app.on_event("startup")
def require_internal_token() -> None:
    if not os.getenv("RUNPOD_INTERNAL_TOKEN"):
        raise RuntimeError("RUNPOD_INTERNAL_TOKEN is required")


class CreateEventRequest(BaseModel):
    user_id: int | None = None
    calendar_id: str = "primary"
    access_token: str
    event_key: str
    source: str = "manual"
    event: dict[str, Any] = Field(default_factory=dict)


def _check_token(token: str | None) -> None:
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
    return {
        "event_id": item.get("id"),
        "html_link": item.get("htmlLink"),
        "duplicate": duplicate,
        "updated": updated,
        "event": event,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/calendar/create-event")
async def create_event(
    payload: CreateEventRequest,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
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
