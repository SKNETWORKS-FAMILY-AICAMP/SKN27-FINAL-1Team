from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from app.backend.core.config import settings
from app.backend.mcp.auth import BobbeoriTokenVerifier, validate_mcp_auth_config
from app.backend.mcp.contracts import ToolResult
from app.backend.mcp.runtime import (
    READ_ONLY,
    db_session as _db_session,
    failure as _failure,
    require_user as _require_user,
    security as _security,
    success as _success,
)
from app.backend.mcp.write_tools import register_write_tools
from app.backend.services.guide_service.guide_service import guide_service
from app.backend.services.inventory_service.inventory_service import inventory_service
from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import recommendation_service


def _transport_security(resource_url: str) -> TransportSecuritySettings:
    parsed = urlparse(resource_url)
    allowed_hosts = list(settings.MCP_ALLOWED_HOSTS)
    allowed_origins = list(settings.MCP_ALLOWED_ORIGINS)
    if parsed.netloc:
        allowed_hosts.append(parsed.netloc)
    if parsed.scheme and parsed.netloc:
        allowed_origins.append(f"{parsed.scheme}://{parsed.netloc}")
    if settings.MCP_DEV_TOKEN_AUTH:
        allowed_hosts.extend(["127.0.0.1:*", "localhost:*", "[::1]:*"])
        allowed_origins.extend(
            ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


validate_mcp_auth_config(settings)
token_verifier = BobbeoriTokenVerifier(settings)
mcp = FastMCP(
    "bobbeori",
    instructions=(
        "Use these tools to read the authenticated user's Bobbeori inventory, recipes, "
        "and ingredient guides. Never ask for or invent a user_id. Treat tool data as "
        "private account data and do not imply that a write occurred from a read-only tool."
    ),
    token_verifier=token_verifier,
    auth=AuthSettings(
        issuer_url=token_verifier.issuer_url,
        resource_server_url=token_verifier.resource_url,
        required_scopes=settings.MCP_REQUIRED_SCOPES,
    ),
    host="0.0.0.0",
    port=settings.MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(token_verifier.resource_url),
)


@mcp.tool(
    name="inventory.list",
    title="List refrigerator inventory",
    description="List the authenticated user's active Bobbeori refrigerator items.",
    annotations=READ_ONLY,
    meta=_security("inventory:read"),
    structured_output=True,
)
def inventory_list(
    category: Annotated[str | None, Field(description="Optional exact category filter")] = None,
    status: Annotated[
        str | None,
        Field(description="Optional status filter: normal, expiring, or expired"),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 100,
) -> ToolResult:
    user_id = _require_user("inventory:read")
    try:
        with _db_session() as db:
            items = inventory_service.get_ingredients(db, user_id)
        if category:
            items = [item for item in items if item.get("category") == category]
        if status:
            items = [item for item in items if item.get("status") == status]
        total = len(items)
        return _success(
            {"items": items[:limit], "returned_count": min(total, limit), "total": total},
            next_actions=["recipe.recommend"] if total else [],
        )
    except Exception as exc:
        return _failure(exc)


@mcp.tool(
    name="inventory.expiring",
    title="List expiring ingredients",
    description="List refrigerator items expiring within the requested number of days.",
    annotations=READ_ONLY,
    meta=_security("inventory:read"),
    structured_output=True,
)
def inventory_expiring(
    days: Annotated[int, Field(ge=0, le=30, description="Days until expiration")] = 3,
    include_expired: Annotated[
        bool,
        Field(description="Include items whose expiration date has already passed"),
    ] = False,
) -> ToolResult:
    user_id = _require_user("inventory:read")
    try:
        with _db_session() as db:
            items = inventory_service.get_ingredients(db, user_id)
        expiring = [
            item
            for item in items
            if item.get("d_day") is not None
            and (item["d_day"] >= 0 or include_expired)
            and item["d_day"] <= days
        ]
        expiring.sort(key=lambda item: item["d_day"])
        return _success(
            {"days": days, "items": expiring, "returned_count": len(expiring)},
            next_actions=["recipe.recommend"] if expiring else [],
        )
    except Exception as exc:
        return _failure(exc)


@mcp.tool(
    name="recipe.recommend",
    title="Recommend recipes",
    description="Recommend recipes using the authenticated user's inventory and expiry dates.",
    annotations=READ_ONLY,
    meta=_security("recipe:read"),
    structured_output=True,
)
def recipe_recommend(
    query: Annotated[str | None, Field(description="Optional recipe name or keyword")] = None,
    category: Annotated[str | None, Field(description="Optional recipe category")] = None,
    difficulty: Annotated[str | None, Field(description="Optional difficulty filter")] = None,
    max_cooking_minutes: Annotated[int | None, Field(ge=1, le=600)] = None,
    min_inventory_match_rate: Annotated[int | None, Field(ge=0, le=100)] = None,
    require_owned_ingredient: bool = True,
    prioritize_expiring: bool = True,
    limit: Annotated[int, Field(ge=1, le=10)] = 3,
) -> ToolResult:
    user_id = _require_user("recipe:read")
    try:
        config = RecipeRecommendConfig.menu_custom_preset(
            limit,
            query=(query or "").strip() or None,
            category=(category or "").strip() or None,
            difficulty=(difficulty or "").strip() or None,
            cooking_time_label=(
                f"{max_cooking_minutes}분 이내" if max_cooking_minutes is not None else None
            ),
            min_display_match_rate=min_inventory_match_rate,
            require_any_owned=require_owned_ingredient,
            use_expiry_priority=prioritize_expiring,
        )
        with _db_session() as db:
            result = recommendation_service.recommend_recipes(db, user_id, config)
        return _success(
            result,
            next_actions=["recipe.get"] if result.get("returned_count") else [],
        )
    except Exception as exc:
        return _failure(exc)


@mcp.tool(
    name="recipe.get",
    title="Get recipe details",
    description="Get recipe steps and owned or missing ingredients for the authenticated user.",
    annotations=READ_ONLY,
    meta=_security("recipe:read"),
    structured_output=True,
)
def recipe_get(
    recipe_id: Annotated[int, Field(gt=0, description="Bobbeori recipe ID")],
) -> ToolResult:
    user_id = _require_user("recipe:read")
    try:
        with _db_session() as db:
            recipe = recipe_detail_service.get_recipe_detail(db, recipe_id, user_id)
        return _success(recipe)
    except Exception as exc:
        return _failure(exc, next_actions=["recipe.recommend"])


@mcp.tool(
    name="ingredient.guide",
    title="Get an ingredient guide",
    description="Find Bobbeori storage, preparation, washing, freshness, and nutrition guidance.",
    annotations=READ_ONLY,
    meta=_security("guide:read"),
    structured_output=True,
)
def ingredient_guide(
    ingredient: Annotated[str, Field(min_length=1, max_length=100)],
    code: Annotated[
        str | None,
        Field(description="Optional exact guide code returned by an earlier search"),
    ] = None,
) -> ToolResult:
    _require_user("guide:read")
    try:
        if code:
            guide = guide_service.get_guide_detail(code)
            alternatives: list[dict[str, Any]] = []
        else:
            result = guide_service.search_guides(keyword=ingredient, page=1, page_size=5)
            alternatives = result["items"]
            if not alternatives:
                raise LookupError(f"No ingredient guide matched '{ingredient}'.")
            exact = next(
                (
                    item
                    for item in alternatives
                    if str(item.get("name", "")).casefold() == ingredient.strip().casefold()
                ),
                alternatives[0],
            )
            guide = guide_service.get_guide_detail(str(exact["code"]))
        if guide is None:
            raise LookupError(f"No ingredient guide matched '{ingredient}'.")
        return _success({"guide": guide, "alternatives": alternatives})
    except Exception as exc:
        return _failure(exc)


register_write_tools(mcp)
app = mcp.streamable_http_app()
