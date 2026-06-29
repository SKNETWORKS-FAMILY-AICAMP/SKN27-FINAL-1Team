import os
from copy import deepcopy
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def _require_internal_token() -> str:
    token = os.getenv("RUNPOD_INTERNAL_TOKEN")
    if not token:
        raise RuntimeError("RUNPOD_INTERNAL_TOKEN is required")
    return token


class InternalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp") and request.headers.get("X-Internal-Token") != _require_internal_token():
            return JSONResponse({"detail": "invalid internal token"}, status_code=401)
        return await call_next(request)


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


def _prepare_event(
    event: dict[str, Any],
    event_key: str,
    source: str,
) -> dict[str, Any]:
    prepared = deepcopy(event)
    private_props = prepared.get("extendedProperties", {}).get("private", {})
    prepared.setdefault("description", "")
    prepared["description"] = prepared["description"].strip()
    prepared["extendedProperties"] = {
        "private": {
            **private_props,
            "bobbeoriKey": event_key,
            "bobbeoriType": _event_type(event_key),
            "bobbeoriSource": source,
        }
    }
    return prepared


def _result(item: dict[str, Any], event: dict[str, Any], duplicate: bool, updated: bool = False) -> dict[str, Any]:
    return {
        "event_id": item.get("id"),
        "html_link": item.get("htmlLink"),
        "duplicate": duplicate,
        "updated": updated,
        "event": event,
    }


async def _find_event(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    event_key: str,
) -> dict[str, Any] | None:
    existing_res = await client.get(
        url,
        headers=headers,
        params={
            "privateExtendedProperty": f"bobbeoriKey={event_key}",
            "singleEvents": "true",
            "maxResults": 1,
        },
    )
    existing_res.raise_for_status()
    return next(iter(existing_res.json().get("items", [])), None)


mcp = FastMCP(
    "bobbeori-calendar",
    host="0.0.0.0",
    port=8000,
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def create_calendar_event(
    access_token: str,
    event_key: str,
    event: dict[str, Any],
    calendar_id: str = "primary",
    source: str = "manual",
    user_id: int | None = None,
) -> dict[str, Any]:
    """Create or update one Bobbeori Google Calendar event."""
    prepared = _prepare_event(event, event_key, source)
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        item = await _find_event(client, url, headers, event_key)
        if item:
            watched = ("summary", "description", "start", "end", "colorId", "reminders", "extendedProperties")
            if any(item.get(field) != prepared.get(field) for field in watched):
                event_res = await client.patch(f"{url}/{item.get('id')}", headers=headers, json=prepared)
                event_res.raise_for_status()
                return _result(event_res.json(), prepared, duplicate=True, updated=True)
            return _result(item, prepared, duplicate=True)

        event_res = await client.post(url, headers=headers, json=prepared)
        event_res.raise_for_status()
        return _result(event_res.json(), prepared, duplicate=False)


@mcp.tool()
async def delete_calendar_event(
    access_token: str,
    event_key: str,
    calendar_id: str = "primary",
    user_id: int | None = None,
) -> dict[str, Any]:
    """Delete one Bobbeori Google Calendar event by bobbeoriKey."""
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        item = await _find_event(client, url, headers, event_key)
        if not item:
            return {"event_key": event_key, "deleted": False, "missing": True}

        event_res = await client.delete(f"{url}/{item.get('id')}", headers=headers)
        event_res.raise_for_status()
        return {"event_key": event_key, "event_id": item.get("id"), "deleted": True, "missing": False}


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


_require_internal_token()
app = mcp.streamable_http_app()
app.add_middleware(InternalTokenMiddleware)
