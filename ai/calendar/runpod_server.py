import os
from copy import deepcopy
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


app = FastAPI(title="Bobbeori Calendar MCP Server")


class PrepareEventRequest(BaseModel):
    user_id: int | None = None
    event_key: str
    source: str = "manual"
    event: dict[str, Any] = Field(default_factory=dict)


def _check_token(token: str | None) -> None:
    expected = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token")


def _event_type(event_key: str, summary: str) -> str:
    if event_key.startswith("ingredient-expiry") or "사용 추천" in summary or "소비" in summary:
        return "ingredient_expiry"
    if event_key.startswith("today-menu") or "저녁 추천" in summary:
        return "dinner_recommendation"
    if event_key.startswith("recipe-delete") or "삭제" in summary or "사라" in summary:
        return "recipe_expiry"
    if "receipt-cost" in event_key or "사용비용" in summary:
        return "receipt_cost"
    return "calendar"


def _default_color(event_type: str, current: str | None) -> str:
    if current:
        return current
    return {
        "ingredient_expiry": "11",
        "dinner_recommendation": "2",
        "recipe_expiry": "5",
        "receipt_cost": "6",
    }.get(event_type, "7")


def _default_reminders(event_type: str, current: dict[str, Any] | None) -> dict[str, Any]:
    if current:
        return current
    minutes = 10 if event_type in {"ingredient_expiry", "dinner_recommendation", "recipe_expiry"} else 0
    return {"useDefault": False, "overrides": [{"method": "popup", "minutes": minutes}]}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/calendar/prepare-event")
def prepare_event(
    payload: PrepareEventRequest,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, dict[str, Any]]:
    _check_token(x_internal_token)
    event = deepcopy(payload.event)
    event_type = _event_type(payload.event_key, event.get("summary", ""))
    private_props = event.get("extendedProperties", {}).get("private", {})

    event["colorId"] = _default_color(event_type, event.get("colorId"))
    event["reminders"] = _default_reminders(event_type, event.get("reminders"))
    event["description"] = (event.get("description") or "").strip()
    event["extendedProperties"] = {
        "private": {
            **private_props,
            "bobbeoriKey": payload.event_key,
            "bobbeoriType": event_type,
            "bobbeoriSource": payload.source,
        }
    }
    return {"event": event}
