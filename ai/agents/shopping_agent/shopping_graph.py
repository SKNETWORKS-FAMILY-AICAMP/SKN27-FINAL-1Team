from __future__ import annotations

import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ai.agents.shopping_agent.shopping_handlers import (
    handle_check_item,
    handle_create_confirm,
    handle_create_request,
    handle_current,
    handle_current_follow_up,
    handle_delete_item_confirm,
    handle_delete_item_request,
    handle_history,
    handle_owned,
    handle_price_help,
    handle_purchase_confirm,
    handle_purchase_request,
    handle_recipe_current,
    handle_recipe_filters,
    handle_selected_product,
)
from ai.agents.shopping_agent.shopping_utils import (
    SHOPPING_AWAITING_PURCHASE,
    SHOPPING_AWAITING_SELECTION,
    SHOPPING_FLOW_SLOT,
    confirm_action,
    extract_ingredient_names,
    extract_recipe_title_for_shopping,
    format_price,
    is_recipe_filter_request,
    is_remaining_request,
    shopping_list_action,
)
from app.backend.services.shopping_service import shopping_service


class ShoppingGraphState(TypedDict, total=False):
    text: str
    db: Any
    user_id: int | None
    history: list[Any]
    intent: str
    slots: dict[str, Any]

    route: str
    search_names: list[str]
    raw_candidates: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    missing_names: list[str]
    selected_index: int

    response_text: str
    actions: list[dict[str, Any]]
    sources: list[dict[str, Any]]


_CANDIDATE_KEYS = (
    "name",
    "provider",
    "product_id",
    "product_name",
    "product_link",
    "price",
    "mall_name",
)

_ORDINALS = {
    "첫번째": 0,
    "첫번": 0,
    "두번째": 1,
    "두번": 1,
    "세번째": 2,
    "세번": 2,
    "네번째": 3,
    "네번": 3,
    "다섯번째": 4,
    "다섯번": 4,
}


def _response(
    message: str,
    *,
    slots: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "response_text": message,
        "actions": list(actions or []),
        "sources": list(sources or []),
        "slots": dict(slots or {}),
    }


def _updated_slots(state: ShoppingGraphState, **updates: Any) -> dict[str, Any]:
    return {**(state.get("slots") or {}), **updates}


def _compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in _CANDIDATE_KEYS if candidate.get(key) is not None}


def _flow(state: ShoppingGraphState) -> dict[str, Any]:
    value = (state.get("slots") or {}).get(SHOPPING_FLOW_SLOT)
    return value if isinstance(value, dict) else {}


def _confirmed_action(text: str) -> tuple[str, str]:
    parts = (text or "").split(":", 2)
    if len(parts) < 2 or parts[0] != "확인":
        return "", ""
    return parts[1], parts[2] if len(parts) >= 3 else ""


def _parse_selection(text: str, candidates: list[dict[str, Any]]) -> int | None:
    if not candidates:
        return None

    action, payload = _confirmed_action(text)
    if action == "shopping_select_product":
        try:
            index = int(payload)
        except (TypeError, ValueError):
            return None
        return index if 0 <= index < len(candidates) else None

    normalized = re.sub(r"\s+", "", text or "").lower()
    if re.fullmatch(r"\d+", normalized):
        index = int(normalized) - 1
        return index if 0 <= index < len(candidates) else None
    numbered = re.search(r"(?:^|\D)(\d+)\s*(?:번|번째)(?:\D|$)", text or "")
    if numbered:
        index = int(numbered.group(1)) - 1
        return index if 0 <= index < len(candidates) else None

    for word, index in _ORDINALS.items():
        if word in normalized and index < len(candidates):
            return index

    if "마지막" in normalized:
        return len(candidates) - 1
    if any(word in normalized for word in ("가장싼", "제일싼", "더싼", "싼걸", "최저가", "저렴한")):
        priced = [(index, item.get("price")) for index, item in enumerate(candidates) if item.get("price")]
        return min(priced, key=lambda item: item[1])[0] if priced else None
    if any(word in normalized for word in ("가장비싼", "제일비싼")):
        priced = [(index, item.get("price")) for index, item in enumerate(candidates) if item.get("price")]
        return max(priced, key=lambda item: item[1])[0] if priced else None

    for index, candidate in enumerate(candidates):
        product_name = re.sub(r"\s+", "", str(candidate.get("product_name") or "")).lower()
        mall_name = re.sub(r"\s+", "", str(candidate.get("mall_name") or "")).lower()
        if len(normalized) >= 2 and (normalized in product_name or normalized == mall_name):
            return index
    return None


def _replacement_query(text: str, current_query: str | None) -> str | None:
    """'두부 말고 순두부'처럼 후보 검색어를 바꾸는 표현을 추출합니다."""
    match = re.search(r"(?:말고|대신)\s*(.+)$", text or "")
    target = match.group(1).strip() if match else ""
    normalized_target = re.sub(r"\s+", "", target).lower()
    if any(word in normalized_target for word in ("싼걸", "저렴한걸", "비싼걸", "최저가")):
        return None
    if not target and "다시" in (text or ""):
        names = extract_ingredient_names(text)
        target = next((name for name in names if name != current_query), "")
    if not target:
        return None
    names = extract_ingredient_names(target)
    return names[0] if names else None


def execute_confirmed_shopping_action(
    action: str,
    payload: str,
    *,
    db: Any,
    user_id: int,
) -> dict[str, Any]:
    if action == "shopping_create":
        names = [name for name in payload.split("|") if name]
        message, actions = handle_create_confirm(db, user_id, names)
        return _response(message, actions=actions)

    if action == "shopping_purchase":
        list_payload, _, item_payload = payload.partition("|")
        shopping_list_id = int(list_payload) if list_payload else None
        item_ids = [int(item_id) for item_id in item_payload.split(",") if item_id] or None
        message, actions = handle_purchase_confirm(db, user_id, shopping_list_id, item_ids)
        return _response(message, actions=actions)

    if action == "shopping_delete_item":
        message, actions = handle_delete_item_confirm(db, user_id, int(payload))
        return _response(message, actions=actions)

    return _response("확인할 장보기 작업을 찾지 못했어요.")


def intent_router_node(state: ShoppingGraphState) -> dict[str, Any]:
    intent = state.get("intent") or "shopping.current"
    text = state.get("text") or ""
    flow = _flow(state)
    action, _ = _confirmed_action(text)

    if action == "shopping_select_product":
        selected_index = _parse_selection(text, flow.get("candidates") or [])
        return {"route": "apply_selected_product" if selected_index is not None else "ask_user_selection", "selected_index": selected_index}
    if action == "shopping_keep_item":
        return {"route": "keep_item"}
    if action == "shopping_cancel_flow" or intent == "shopping.cancel":
        return {"route": "cancel"}
    if action == "shopping_purchase" and flow.get("step") == SHOPPING_AWAITING_PURCHASE:
        return {"route": "stock_inventory"}

    if flow.get("step") == SHOPPING_AWAITING_SELECTION:
        replacement_query = _replacement_query(text, flow.get("query"))
        if replacement_query:
            return {"route": "search_products", "text": replacement_query}
        selected_index = _parse_selection(text, flow.get("candidates") or [])
        if selected_index is not None:
            return {"route": "apply_selected_product", "selected_index": selected_index}
        return {"route": "ask_user_selection"}

    if flow.get("step") == SHOPPING_AWAITING_PURCHASE:
        if intent == "shopping.purchase":
            return {"route": "stock_inventory"}
        return {"route": "confirm_purchase"}

    if intent == "shopping.compare":
        return {"route": "search_products"}
    return {"route": "legacy"}


def _route_after_intent(state: ShoppingGraphState) -> str:
    return state.get("route") or "legacy"


def search_products_node(state: ShoppingGraphState) -> dict[str, Any]:
    names = extract_ingredient_names(state.get("text") or "")
    if not names:
        previous_query = _flow(state).get("query") or (state.get("slots") or {}).get("shopping_product")
        names = [str(previous_query)] if previous_query else []

    display = 5 if len(names) == 1 else 3
    rows: list[dict[str, Any]] = []
    missing_names: list[str] = []
    for name in names:
        result = shopping_service.search_products(name, display=display)
        items = result.get("items") or []
        if not items:
            missing_names.append(name)
            continue
        rows.extend(items)
    return {"search_names": names, "raw_candidates": rows, "missing_names": missing_names}


def filter_candidates_node(state: ShoppingGraphState) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in state.get("raw_candidates") or []:
        candidate = _compact_candidate(raw)
        key = (str(candidate.get("provider") or ""), str(candidate.get("product_id") or candidate.get("product_link") or ""))
        if not candidate.get("product_name") or not key[1] or key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= 5:
            break
    return {"candidates": candidates}


def ask_user_selection_node(state: ShoppingGraphState) -> dict[str, Any]:
    candidates = state.get("candidates") or _flow(state).get("candidates") or []
    if not candidates:
        return _response(
            "적절한 상품 후보를 찾지 못했어요. 상품명이나 용량을 더 구체적으로 입력해 주세요.",
            slots=_updated_slots(state, **{SHOPPING_FLOW_SLOT: None}),
        )

    names = state.get("search_names") or [_flow(state).get("query")]
    query = next((str(name) for name in names if name), str(candidates[0].get("name") or ""))
    lines = ["네이버 쇼핑 기준 상품 후보예요."]
    actions: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        product_name = candidate.get("product_name") or candidate.get("name") or "상품명 없음"
        market = candidate.get("mall_name") or candidate.get("provider") or "마켓 정보 없음"
        lines.append(f"{index}. {product_name} - {format_price(candidate.get('price'))} ({market})")
        actions.append(confirm_action(f"{index}번 담기", f"확인:shopping_select_product:{index - 1}"))
        if candidate.get("product_link"):
            sources.append({"title": f"{index}. {product_name}", "url": candidate["product_link"]})
    for missing_name in state.get("missing_names") or []:
        lines.append(f"{missing_name}은 적절한 상품 후보를 찾지 못했어요.")
    lines.append("번호를 선택하면 해당 상품을 장보기 목록에 반영할게요.")
    actions.append(confirm_action("선택 취소", "확인:shopping_cancel_flow:"))

    flow = {
        "step": SHOPPING_AWAITING_SELECTION,
        "query": query,
        "candidates": candidates,
    }
    return _response(
        "\n".join(lines),
        actions=actions,
        sources=sources,
        slots=_updated_slots(state, shopping_product=query, **{SHOPPING_FLOW_SLOT: flow}),
    )


def apply_selected_product_node(state: ShoppingGraphState) -> dict[str, Any]:
    flow = _flow(state)
    candidates = flow.get("candidates") or []
    selected_index = state.get("selected_index")
    if selected_index is None or not 0 <= selected_index < len(candidates):
        return {"candidates": candidates}

    candidate = candidates[selected_index]
    shopping_list, selected_item = handle_selected_product(
        state.get("db"),
        int(state.get("user_id") or 0),
        candidate,
    )
    next_flow = {
        "step": SHOPPING_AWAITING_PURCHASE,
        "query": flow.get("query") or candidate.get("name"),
        "selected_product": candidate,
        "shopping_list_id": shopping_list.get("id"),
        "shopping_item_id": selected_item.get("id"),
    }
    return {
        "slots": _updated_slots(state, **{SHOPPING_FLOW_SLOT: next_flow}),
        "route": "confirm_purchase",
    }


def confirm_purchase_node(state: ShoppingGraphState) -> dict[str, Any]:
    flow = _flow(state)
    candidate = flow.get("selected_product") or {}
    product_name = candidate.get("product_name") or candidate.get("name") or "선택한 상품"
    list_id = flow.get("shopping_list_id")
    item_id = flow.get("shopping_item_id")
    if not list_id or not item_id:
        return _response(
            "선택 상품은 장보기 목록에 반영했지만 구매 확인 정보를 찾지 못했어요. 장보기 목록에서 다시 확인해주세요.",
            actions=[shopping_list_action(list_id)],
            slots=_updated_slots(state, **{SHOPPING_FLOW_SLOT: None}),
        )

    return _response(
        f"{product_name}을 장보기 목록에 반영했어요. 구매하셨다면 바로 냉장고에 입고할까요?",
        actions=[
            confirm_action("구매 완료 · 냉장고 입고", f"확인:shopping_purchase:{list_id}|{item_id}"),
            confirm_action("나중에 구매", "확인:shopping_keep_item:"),
            shopping_list_action(list_id),
        ],
        slots=state.get("slots") or {},
    )


def stock_inventory_node(state: ShoppingGraphState) -> dict[str, Any]:
    flow = _flow(state)
    action, payload = _confirmed_action(state.get("text") or "")
    if action == "shopping_purchase" and payload:
        list_payload, _, item_payload = payload.partition("|")
        shopping_list_id = int(list_payload) if list_payload else None
        item_ids = [int(item_id) for item_id in item_payload.split(",") if item_id] or None
    else:
        shopping_list_id = int(flow.get("shopping_list_id")) if flow.get("shopping_list_id") else None
        item_ids = [int(flow["shopping_item_id"])] if flow.get("shopping_item_id") else None

    message, actions = handle_purchase_confirm(
        state.get("db"),
        int(state.get("user_id") or 0),
        shopping_list_id,
        item_ids,
    )
    return _response(
        message,
        actions=actions,
        slots=_updated_slots(state, shopping_product=None, **{SHOPPING_FLOW_SLOT: None}),
    )


def keep_item_node(state: ShoppingGraphState) -> dict[str, Any]:
    flow = _flow(state)
    return _response(
        "장보기 목록에 남겨둘게요. 구매한 뒤 구매 완료를 알려주시면 냉장고에 입고할게요.",
        actions=[shopping_list_action(flow.get("shopping_list_id"))],
        slots=_updated_slots(state, **{SHOPPING_FLOW_SLOT: None}),
    )


def cancel_flow_node(state: ShoppingGraphState) -> dict[str, Any]:
    flow = _flow(state)
    if flow.get("step") == SHOPPING_AWAITING_PURCHASE:
        message = "구매 확인은 취소했어요. 선택한 상품은 장보기 목록에 남겨둘게요."
        actions = [shopping_list_action(flow.get("shopping_list_id"))]
    else:
        message = "상품 선택을 취소했어요."
        actions = []
    return _response(
        message,
        actions=actions,
        slots=_updated_slots(state, **{SHOPPING_FLOW_SLOT: None}),
    )


def legacy_action_node(state: ShoppingGraphState) -> dict[str, Any]:
    text = state.get("text") or ""
    db = state.get("db")
    user_id = int(state.get("user_id") or 0)
    slots = state.get("slots") or {}
    intent = state.get("intent") or "shopping.current"

    if intent == "shopping.price_help":
        message, actions = handle_price_help()
        return _response(message, actions=actions, slots=slots)
    if intent == "action.cancel":
        return _response("알겠어요. 장보기 작업을 취소했어요.", slots=slots)
    if intent == "action.confirm":
        action, payload = _confirmed_action(text)
        result = execute_confirmed_shopping_action(action, payload, db=db, user_id=user_id)
        result["slots"] = slots
        return result

    if intent == "shopping.current":
        recipe_title = extract_recipe_title_for_shopping(text)
        if is_recipe_filter_request(text):
            message, actions, next_slots = handle_recipe_filters(db, user_id)
        elif recipe_title:
            message, actions, next_slots = handle_recipe_current(db, user_id, recipe_title)
        elif is_remaining_request(text) and slots:
            message, actions, next_slots = handle_current_follow_up(db, user_id, text, slots)
        else:
            message, actions, next_slots = handle_current(db, user_id)
    elif intent == "shopping.owned":
        message, actions = handle_owned(db, user_id, slots)
        next_slots = slots
    elif intent == "shopping.history":
        message, actions = handle_history(db, user_id)
        next_slots = slots
    elif intent == "shopping.create":
        message, actions = handle_create_request(text)
        next_slots = slots
    elif intent == "shopping.purchase":
        message, actions = handle_purchase_request(db, user_id, text)
        next_slots = slots
    elif intent == "shopping.delete_item":
        message, actions = handle_delete_item_request(db, user_id, text)
        next_slots = slots
    elif intent == "shopping.check_item":
        message, actions = handle_check_item(db, user_id, text)
        next_slots = slots
    else:
        message = "장보기 요청을 이해하지 못했어요. 목록 조회, 가격 비교, 구매 완료를 요청할 수 있어요."
        actions = []
        next_slots = slots
    return _response(message, actions=actions, slots=next_slots)


workflow = StateGraph(ShoppingGraphState)
workflow.add_node("intent_router", intent_router_node)
workflow.add_node("search_products", search_products_node)
workflow.add_node("filter_candidates", filter_candidates_node)
workflow.add_node("ask_user_selection", ask_user_selection_node)
workflow.add_node("apply_selected_product", apply_selected_product_node)
workflow.add_node("confirm_purchase", confirm_purchase_node)
workflow.add_node("stock_inventory", stock_inventory_node)
workflow.add_node("keep_item", keep_item_node)
workflow.add_node("cancel_flow", cancel_flow_node)
workflow.add_node("legacy_action", legacy_action_node)

workflow.set_entry_point("intent_router")
workflow.add_conditional_edges(
    "intent_router",
    _route_after_intent,
    {
        "search_products": "search_products",
        "ask_user_selection": "ask_user_selection",
        "apply_selected_product": "apply_selected_product",
        "confirm_purchase": "confirm_purchase",
        "stock_inventory": "stock_inventory",
        "keep_item": "keep_item",
        "cancel": "cancel_flow",
        "legacy": "legacy_action",
    },
)
workflow.add_edge("search_products", "filter_candidates")
workflow.add_edge("filter_candidates", "ask_user_selection")
workflow.add_edge("apply_selected_product", "confirm_purchase")
for node_name in (
    "ask_user_selection",
    "confirm_purchase",
    "stock_inventory",
    "keep_item",
    "cancel_flow",
    "legacy_action",
):
    workflow.add_edge(node_name, END)

shopping_agent_graph = workflow.compile()
