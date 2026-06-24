import os
from datetime import date
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


app = FastAPI(title="Bobbeori Calendar MCP Server")


class CalendarEvent(BaseModel):
    id: str | None = None
    dateKey: str
    title: str
    colorId: str | None = None
    htmlLink: str | None = None


class CalendarEventsRequest(BaseModel):
    user_id: int
    start_date: date
    end_date: date
    events: list[CalendarEvent] = Field(default_factory=list)


def _check_token(token: str | None) -> None:
    expected = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid internal token")


def _event_type(title: str) -> str:
    if "사용 추천" in title or "소비" in title:
        return "ingredient_expiry"
    if "저녁 추천" in title:
        return "dinner_recommendation"
    if "삭제" in title or "사라" in title:
        return "recipe_expiry"
    if "사용비용" in title:
        return "receipt_cost"
    return "calendar"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/calendar/events")
def calendar_events(
    payload: CalendarEventsRequest,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, list[dict[str, Any]]]:
    _check_token(x_internal_token)
    return {
        "events": [
            {
                **event.model_dump(),
                "eventType": _event_type(event.title),
            }
            for event in payload.events
        ]
    }
