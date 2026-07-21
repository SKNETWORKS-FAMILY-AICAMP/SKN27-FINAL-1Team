from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timezone
from typing import Annotated, Any, Awaitable, Callable, Literal

from fastapi.encoders import jsonable_encoder
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy.orm import Session

from ai.agents.alarm_agent.tools import create_calendar_event_tool
from app.backend.api.calendar import calendar_api
from app.backend.api.receipts import receipts_api
from app.backend.core.config import settings
from app.backend.db.models import Receipt
from app.backend.mcp.confirmation import (
    claim_mutation,
    complete_mutation,
    fail_mutation,
    issue_preview_token,
    verify_preview_token,
)
from app.backend.mcp.contracts import ToolResult
from app.backend.mcp.runtime import db_session, failure, require_user, security, success
from app.backend.schemas.receipts import ReceiptConfirmItem, ReceiptConfirmRequest
from app.backend.schemas.shopping import ShoppingIngredientInput
from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service
from app.backend.services.shopping_service import shopping_service


PREVIEW = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
SAVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
REPLACE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)
EXTERNAL_CREATE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _preview_result(
    action: str,
    user_id: int,
    payload: dict[str, Any],
    preview: dict[str, Any],
    warnings: list[str] | None = None,
) -> ToolResult:
    token, _ = issue_preview_token(action, user_id, jsonable_encoder(payload))
    return success(
        {
            "preview": preview,
            "confirmation_token": token,
            "expires_in_seconds": settings.MCP_PREVIEW_TTL_SECONDS,
        },
        warnings=warnings,
        requires_confirmation=True,
        next_actions=[action],
    )


async def _run_confirmed(
    *,
    action: str,
    user_id: int,
    confirmation_token: str,
    confirmed: bool,
    executor: Callable[[Session, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]],
) -> ToolResult:
    if confirmed is not True:
        return failure(ValueError("Explicit confirmation is required. Run preview and confirm it first."))

    mutation_id: int | None = None
    try:
        payload, idempotency_key = verify_preview_token(confirmation_token, action, user_id)
        with db_session() as db:
            mutation, cached = claim_mutation(
                db,
                user_id=user_id,
                action=action,
                idempotency_key=idempotency_key,
            )
            mutation_id = int(mutation.id)
            if cached is not None:
                return success({**cached, "idempotent_replay": True})

            try:
                result = executor(db, payload)
                if inspect.isawaitable(result):
                    result = await result
                encoded = jsonable_encoder(result)
                complete_mutation(db, mutation_id, encoded)
                return success({**encoded, "idempotent_replay": False})
            except Exception as exc:
                fail_mutation(db, mutation_id, exc)
                raise
    except Exception as exc:
        return failure(exc, next_actions=[action.replace("create", "preview").replace("commit", "preview").replace("save", "preview")])


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone offset, for example +09:00.")
    return value


def _event_key(action: str, user_id: int, title: str, start_at: datetime) -> str:
    digest = hashlib.sha256(f"{action}|{title}|{start_at.isoformat()}".encode()).hexdigest()[:16]
    return f"calendar-agent-{user_id}-{digest}"


def _calendar_payload(
    *,
    action: str,
    user_id: int,
    title: str,
    start_at: datetime,
    duration_minutes: int,
    description: str | None,
    reminder_type: str,
    reminder_minutes_before: int,
) -> dict[str, Any]:
    return {
        "title": title.strip(),
        "start_at": start_at.isoformat(),
        "duration_minutes": duration_minutes,
        "description": (description or "").strip() or None,
        "reminder_type": reminder_type,
        "reminder_minutes_before": reminder_minutes_before,
        "event_key": _event_key(action, user_id, title.strip(), start_at),
    }


async def _execute_calendar(db: Session, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    result = await create_calendar_event_tool(payload, {"db": db, "user_id": user_id})
    if not result.get("ok"):
        error = result.get("error", {})
        raise ValueError(str(error.get("message") or "Calendar creation failed."))
    return dict(result.get("data") or {})


def register_write_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="receipt.preview",
        title="Preview receipt commit",
        description="Use this when the user wants to review receipt items before stocking them in Bobbeori.",
        annotations=PREVIEW,
        meta=security("receipt:write"),
        structured_output=True,
    )
    def receipt_preview(
        receipt_id: Annotated[int, Field(gt=0)],
        items: Annotated[list[ReceiptConfirmItem], Field(min_length=1, max_length=100)],
        store_name: Annotated[str | None, Field(max_length=100)] = None,
        purchase_datetime: Annotated[str | None, Field(description="ISO or YYYY-MM-DD HH:mm:ss")] = None,
        total_amount: Annotated[int | None, Field(ge=0)] = None,
        calendar_cost_enabled: bool = False,
    ) -> ToolResult:
        user_id = require_user("receipt:write")
        try:
            request = ReceiptConfirmRequest(
                receipt_id=receipt_id,
                store_name=store_name,
                purchase_datetime=purchase_datetime,
                total_amount=total_amount,
                items=items,
                calendar_cost_enabled=calendar_cost_enabled,
            )
            with db_session() as db:
                exists = (
                    db.query(Receipt.id)
                    .filter(Receipt.id == receipt_id, Receipt.user_id == user_id)
                    .first()
                )
            if not exists:
                raise LookupError("Receipt not found for the authenticated user.")

            line_total = sum(item.item_amount or 0 for item in items)
            warnings = []
            if total_amount is not None and line_total and total_amount != line_total:
                warnings.append("The receipt total differs from the sum of the line items.")
            if calendar_cost_enabled:
                warnings.append("Commit may also create or update a Google Calendar cost event.")
            payload = request.model_dump(mode="json")
            return _preview_result(
                "receipt.commit",
                user_id,
                payload,
                {
                    "receipt_id": receipt_id,
                    "store_name": store_name,
                    "purchase_datetime": purchase_datetime,
                    "item_count": len(items),
                    "line_item_total": line_total,
                    "total_amount": total_amount,
                    "calendar_cost_enabled": calendar_cost_enabled,
                    "items": [item.model_dump(mode="json") for item in items],
                },
                warnings,
            )
        except Exception as exc:
            return failure(exc)

    @mcp.tool(
        name="receipt.commit",
        title="Commit receipt items",
        description="Use this only after receipt.preview and explicit user confirmation; it replaces prior confirmation for that receipt and stocks the items.",
        annotations=REPLACE,
        meta=security("receipt:write"),
        structured_output=True,
    )
    async def receipt_commit(
        confirmation_token: str,
        confirmed: Literal[True],
    ) -> ToolResult:
        user_id = require_user("receipt:write")

        async def execute(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
            request = ReceiptConfirmRequest.model_validate(payload)
            response = await receipts_api.confirm_receipt_items(
                request_data=request,
                current_user_id=user_id,
                db=db,
            )
            receipt = (
                db.query(Receipt)
                .filter(Receipt.id == request.receipt_id, Receipt.user_id == user_id)
                .one()
            )
            saved_items = (receipt.confirmed_result_json or {}).get("items", [])
            return {
                "receipt_id": request.receipt_id,
                "saved_item_count": len(saved_items),
                **response,
            }

        return await _run_confirmed(
            action="receipt.commit",
            user_id=user_id,
            confirmation_token=confirmation_token,
            confirmed=confirmed,
            executor=execute,
        )

    @mcp.tool(
        name="shopping.preview",
        title="Preview shopping-list save",
        description="Use this when the user wants to review ingredients before adding them to the Bobbeori shopping list.",
        annotations=PREVIEW,
        meta=security("shopping:write"),
        structured_output=True,
    )
    def shopping_preview(
        recipe_id: Annotated[int | None, Field(gt=0)] = None,
        ingredients: Annotated[
            list[ShoppingIngredientInput] | None,
            Field(max_length=100, description="Items to save; omitted to use a recipe's missing ingredients"),
        ] = None,
    ) -> ToolResult:
        user_id = require_user("shopping:write")
        try:
            selected = list(ingredients or [])
            with db_session() as db:
                recipe_title = None
                if recipe_id is not None:
                    detail = recipe_detail_service.get_recipe_detail(db, recipe_id, user_id)
                    recipe_title = detail.get("title")
                    if not selected:
                        selected = [
                            ShoppingIngredientInput(
                                ingredient_id=item.get("ingredient_id"),
                                name=item["name"],
                                amount=item.get("amount"),
                            )
                            for item in detail.get("missing_ingredients", [])
                            if item.get("name")
                        ]
            if not selected:
                raise ValueError("No ingredients remain to add to the shopping list.")

            payload = {
                "recipe_id": recipe_id,
                "source": "recipe" if recipe_id is not None else "manual",
                "ingredients": [item.model_dump(mode="json") for item in selected],
            }
            return _preview_result(
                "shopping.save",
                user_id,
                payload,
                {
                    "recipe_id": recipe_id,
                    "recipe_title": recipe_title,
                    "item_count": len(selected),
                    "items": payload["ingredients"],
                },
                ["Product links and current prices are resolved when the list is saved."],
            )
        except Exception as exc:
            return failure(exc)

    @mcp.tool(
        name="shopping.save",
        title="Save shopping list",
        description="Use this only after shopping.preview and explicit user confirmation; it adds or merges the reviewed items.",
        annotations=SAVE,
        meta=security("shopping:write"),
        structured_output=True,
    )
    async def shopping_save(
        confirmation_token: str,
        confirmed: Literal[True],
    ) -> ToolResult:
        user_id = require_user("shopping:write")

        def execute(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
            items = [ShoppingIngredientInput.model_validate(item) for item in payload["ingredients"]]
            return shopping_service.create_list(
                db=db,
                user_id=user_id,
                recipe_id=payload.get("recipe_id"),
                source=payload["source"],
                missing_ingredients=items,
            )

        return await _run_confirmed(
            action="shopping.save",
            user_id=user_id,
            confirmation_token=confirmation_token,
            confirmed=confirmed,
            executor=execute,
        )

    @mcp.tool(
        name="calendar.preview",
        title="Preview calendar event",
        description="Use this when the user wants to review a general Google Calendar event before creation.",
        annotations=PREVIEW,
        meta=security("calendar:write"),
        structured_output=True,
    )
    def calendar_preview(
        title: Annotated[str, Field(min_length=1, max_length=200)],
        start_at: datetime,
        duration_minutes: Annotated[int, Field(ge=5, le=1440)] = 30,
        description: Annotated[str | None, Field(max_length=2000)] = None,
        reminder_minutes_before: Annotated[int, Field(ge=0, le=10080)] = 10,
    ) -> ToolResult:
        user_id = require_user("calendar:write")
        try:
            start_at = _aware(start_at, "start_at")
            with db_session() as db:
                calendar_api._get_google_integration(db, user_id)
            payload = _calendar_payload(
                action="calendar.create",
                user_id=user_id,
                title=title,
                start_at=start_at,
                duration_minutes=duration_minutes,
                description=description,
                reminder_type="calendar_event",
                reminder_minutes_before=reminder_minutes_before,
            )
            warnings = []
            if start_at < datetime.now(timezone.utc).astimezone(start_at.tzinfo):
                warnings.append("The event starts in the past.")
            return _preview_result("calendar.create", user_id, payload, payload, warnings)
        except Exception as exc:
            return failure(exc)

    @mcp.tool(
        name="calendar.create",
        title="Create calendar event",
        description="Use this only after calendar.preview and explicit user confirmation; it creates or updates the reviewed Google Calendar event.",
        annotations=EXTERNAL_CREATE,
        meta=security("calendar:write"),
        structured_output=True,
    )
    async def calendar_create(
        confirmation_token: str,
        confirmed: Literal[True],
    ) -> ToolResult:
        user_id = require_user("calendar:write")
        return await _run_confirmed(
            action="calendar.create",
            user_id=user_id,
            confirmation_token=confirmation_token,
            confirmed=confirmed,
            executor=lambda db, payload: _execute_calendar(db, user_id, payload),
        )

    @mcp.tool(
        name="reminder.preview",
        title="Preview reminder",
        description="Use this when the user wants to review a food-use or shopping reminder before creating it in Google Calendar.",
        annotations=PREVIEW,
        meta=security("calendar:write"),
        structured_output=True,
    )
    def reminder_preview(
        title: Annotated[str, Field(min_length=1, max_length=200)],
        remind_at: datetime,
        reminder_type: Literal["consume_reminder", "shopping_reminder"],
        description: Annotated[str | None, Field(max_length=2000)] = None,
    ) -> ToolResult:
        user_id = require_user("calendar:write")
        try:
            remind_at = _aware(remind_at, "remind_at")
            if remind_at <= datetime.now(timezone.utc).astimezone(remind_at.tzinfo):
                raise ValueError("remind_at must be in the future.")
            with db_session() as db:
                calendar_api._get_google_integration(db, user_id)
            payload = _calendar_payload(
                action="reminder.create",
                user_id=user_id,
                title=title,
                start_at=remind_at,
                duration_minutes=10,
                description=description,
                reminder_type=reminder_type,
                reminder_minutes_before=0,
            )
            return _preview_result("reminder.create", user_id, payload, payload)
        except Exception as exc:
            return failure(exc)

    @mcp.tool(
        name="reminder.create",
        title="Create reminder",
        description="Use this only after reminder.preview and explicit user confirmation; it creates or updates the reviewed reminder.",
        annotations=EXTERNAL_CREATE,
        meta=security("calendar:write"),
        structured_output=True,
    )
    async def reminder_create(
        confirmation_token: str,
        confirmed: Literal[True],
    ) -> ToolResult:
        user_id = require_user("calendar:write")
        return await _run_confirmed(
            action="reminder.create",
            user_id=user_id,
            confirmation_token=confirmation_token,
            confirmed=confirmed,
            executor=lambda db, payload: _execute_calendar(db, user_id, payload),
        )
