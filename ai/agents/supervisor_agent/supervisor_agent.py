import logging
import re

from langgraph.graph import END, StateGraph

from ai.agents.inventory_agent.inventory_utils import (
    _pending_add_many_from_history,
    _is_quantity_only_list,
    _extract_storage,
    _pending_add_storage_from_history,
    _pending_add_from_history,
    _pending_consume_from_history,
    _extract_add_items,
    _extract_quantity,
    _is_all_quantity_request,
    _is_storage_change_request,
    ADD_WORDS,
    DELETE_WORDS,
    CONSUME_WORDS,
    INVENTORY_LIST_WORDS,
)

from app.backend.schemas.chat_state import GraphState
from ai.agents.recipe_agent import run_recipe_agent

from ai.agents.supervisor_agent.agent_execution import (
    _agent_result_failed,
    _merge_agent_results,
    _normalize_agent_result,
    _run_agent_with_retry,
)
from ai.agents.supervisor_agent.chat_context import (
    _is_context_follow_up,
    _latest_bot_intent,
    _latest_bot_pending_action,
    _latest_bot_slots,
    _rewrite_context_switch,
)
from ai.agents.supervisor_agent.chat_response_mapper import _alarm_result_to_state
from ai.agents.supervisor_agent.routing_rules import (
    _build_read_tasks,
    _is_alarm_calendar_query,
    _is_alarm_notification_query,
    _is_alarm_write_query,
    _is_guide_query,
    _is_receipt_lookup_query,
    _is_receipt_query,
    _is_recipe_pairing_query,
    _is_recipe_recommend_query,
    _is_recipe_search_query,
    _is_shopping_price_explanation,
    _is_shopping_price_query,
    _is_cooking_time_question,
    _is_expiring_question,
    _is_food_general_query,
    _normalize_text,
    _route_result,
)
from ai.agents.supervisor_agent.supervisor_utils import (
    CANCEL_WORDS,
    CONFIRM_PREFIX,
    SIGNED_CONFIRM_PREFIX,
    GENERAL_REPLY,
    LOGIN_REQUIRED_REPLY,
    _ALARM_CONFIRM_ACTIONS,
    _INVENTORY_CONFIRM_ACTIONS,
    _LLM_ROUTE_CONFIDENCE,
    _SHOPPING_WRITE_INTENTS,
    _is_shopping_show_all_request,
    _inherit_route_context,
    _is_shopping_history_request,
    _normalize_shopping_create_query,
    _shopping_requested_quantity,
    _should_use_food_fallback,
    _truncated_shopping_count,
    _normalize_shopping_delete_query,
    _parse_alarm_request,
    _rewrite_guide_query,
    _strip_shopping_compare_suffix,
    _verify_and_claim_confirm_token,
)
from ai.agents.shopping_agent.shopping_utils import (
    SHOPPING_CONFIRM_ACTIONS,
    analyze_shopping_intent,
    pending_shopping_flow_intent,
)

logger = logging.getLogger(__name__)


def _route_write_request(
    text: str,
    previous_intent: str | None,
    previous_slots: dict,
    is_receipt_query: bool,
) -> dict | None:
    """데이터를 변경할 수 있는 요청만 LLM보다 먼저 규칙으로 분류합니다."""
    normalized = _normalize_text(text)
    is_shopping_stock_in = not is_receipt_query and "입고" in normalized and (
        "냉장고" in normalized
        or bool(previous_intent and previous_intent.startswith("shopping."))
    )

    if is_shopping_stock_in:
        return _route_result("shopping.purchase", slots=previous_slots)

    if (
        previous_intent == "ingredient.guide"
        and any(phrase in normalized for phrase in ("넣으면되", "넣어도되", "둬도되", "두면되", "보관해도되"))
    ):
        # 보관 가능 여부를 묻는 후속 질문은 냉장고 추가 명령으로 처리하지 않습니다.
        return _route_result("ingredient.guide", slots=previous_slots)

    if previous_intent == "shopping.delete_item" and analyze_shopping_intent(f"장보기 {text}") == "shopping.delete_item":
        return _route_result("shopping.delete_item", slots=previous_slots)

    # 생략된 쓰기 명령은 일반 냉장고 규칙보다 직전 Agent 문맥을 우선합니다.
    has_write_word = any(word in normalized for word in (*DELETE_WORDS, *CONSUME_WORDS, *ADD_WORDS))
    if previous_intent and has_write_word and _is_context_follow_up(text):
        if previous_intent.startswith("shopping."):
            return _route_result(analyze_shopping_intent(f"장보기 {text}") or previous_intent, slots=previous_slots)
        if previous_intent.startswith("alarm."):
            return _route_result(previous_intent, slots=previous_slots)

    if _is_alarm_write_query(text):
        intent = "alarm.notification" if _is_alarm_notification_query(text) else "alarm.calendar"
        return _route_result(intent)

    shopping_intent = analyze_shopping_intent(text)
    if shopping_intent in _SHOPPING_WRITE_INTENTS:
        return _route_result(shopping_intent)
    if not is_receipt_query and _is_storage_change_request(text):
        return _route_result("inventory.storage_change")
    if not is_receipt_query and any(word in normalized for word in DELETE_WORDS):
        return _route_result("inventory.delete")
    if not is_receipt_query and not _is_expiring_question(text) and any(word in normalized for word in CONSUME_WORDS):
        return _route_result("inventory.action")
    if not is_receipt_query and not _is_guide_query(text) and any(word in normalized for word in ADD_WORDS):
        return _route_result("inventory.action")
    return None


def _route_read_fallback(
    text: str,
    history: list,
    previous_intent: str | None,
    previous_slots: dict,
    is_receipt_query: bool,
) -> dict:
    """LLM을 사용할 수 없거나 신뢰도가 낮을 때 읽기 요청을 최소 규칙으로 보완합니다."""
    normalized = _normalize_text(text)
    shopping_intent = analyze_shopping_intent(text)

    if _is_receipt_lookup_query(text):
        return _route_result("receipt.lookup")
    if is_receipt_query:
        return _route_result("receipt.guide")
    if (
        previous_intent == "shopping.compare"
        and previous_slots.get("shopping_product")
        and not _strip_shopping_compare_suffix(text)
    ):
        return _route_result("shopping.compare", slots=previous_slots)
    if previous_intent == "shopping.current" and _is_shopping_show_all_request(text):
        return _route_result("shopping.current", slots=previous_slots)
    if _is_alarm_notification_query(text):
        return _route_result("alarm.notification")
    if _is_alarm_calendar_query(text):
        return _route_result("alarm.calendar")
    if _is_shopping_price_explanation(text):
        return _route_result("shopping.price_help")
    read_tasks = _build_read_tasks(text)
    if len(read_tasks) >= 2:
        return _route_result("multi_agent", tasks=read_tasks)
    if _is_shopping_price_query(text):
        return _route_result("shopping.compare")
    if _is_guide_query(text):
        return _route_result("ingredient.guide")
    if "장본" in normalized:
        return _route_result("shopping.current")
    if shopping_intent:
        return _route_result(shopping_intent)
    if _is_recipe_pairing_query(text):
        return _route_result("recipe.pairing")
    if _is_expiring_question(text):
        return _route_result("inventory.expiring")
    if _is_cooking_time_question(text):
        return _route_result("recipe.search")
    if previous_intent and _is_context_follow_up(text):
        return _route_result(previous_intent, slots=previous_slots)
    if _is_recipe_recommend_query(text):
        return _route_result("recipe.recommend")
    if (
        not _is_guide_query(text)
        and not _is_alarm_calendar_query(text)
        and not _is_expiring_question(text)
        and any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS)
    ):
        return _route_result("inventory.list")
    if _is_recipe_search_query(text):
        return _route_result("recipe.search")
    return _route_result("general")





def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    original_text = state["text"]
    history = state.get("history", [])
    trusted_context = state.get("trusted_context") or {}
    context_enforced = bool(state.get("context_enforced"))
    trusted_intent = trusted_context.get("intent")
    trusted_slots = trusted_context.get("slots") or {}
    previous_intent = trusted_intent or _latest_bot_intent(history)
    previous_slots = trusted_slots or _latest_bot_slots(history)
    write_previous_intent = trusted_intent if context_enforced else previous_intent
    write_previous_slots = trusted_slots if context_enforced else previous_slots
    inventory_pending = write_previous_slots.get("inventory_pending")
    inventory_last_action = write_previous_slots.get("inventory_last_action")
    legacy_pending_allowed = not context_enforced
    has_pending = bool(
        inventory_pending
        or (
            legacy_pending_allowed
            and (
                _pending_add_many_from_history(history)
                or _pending_add_storage_from_history(history)
                or _pending_add_from_history(history)
                or _pending_consume_from_history(history)
                or _latest_bot_pending_action(history)
            )
        )
    )
    text = _rewrite_context_switch(original_text, has_pending)

    # 번복 뒤 새 명령은 오래된 pending 문맥을 버리고 처음부터 다시 분류합니다.
    if text != original_text:
        keep_delete_context = (
            isinstance(inventory_pending, dict)
            and inventory_pending.get("action") in {"delete_quantity", "delete_confirm"}
            and (_extract_quantity(text) is not None or _is_all_quantity_request(text))
        )
        next_history = history if keep_delete_context else []
        result = router_node({**state, "text": text, "history": next_history})
        result.update({"text": text, "history": next_history})
        return result

    normalized = _normalize_text(text)
    # "장본 거"는 냉장고 재료 목록이 아니라 장보기 목록 조회로 우선 처리합니다.
    if "장본" in normalized:
        return _route_result("shopping.current")
    # 장보기 기능 문의는 "뭐 있어" 표현보다 장보기 문맥을 우선합니다.
    if "장보기" in normalized:
        return _route_result(analyze_shopping_intent(text) or "shopping.current")
    # 목록 조회 표현은 등록 같은 단어가 포함돼도 재료 추가 요청으로 처리하지 않습니다.
    if (
        not _is_guide_query(text)
        and not _is_alarm_calendar_query(text)
        and not _is_expiring_question(text)
        and any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS)
    ):
        return _route_result("inventory.list")
    is_receipt_query = _is_receipt_query(text)

    if text.startswith(SIGNED_CONFIRM_PREFIX):
        command = _verify_and_claim_confirm_token(text, state.get("user_id"))
        if not command:
            return _route_result("action.invalid")
        result = _route_result("action.confirm")
        result["text"] = command
        return result
    if normalized.startswith(CONFIRM_PREFIX):
        return _route_result("action.invalid")
    if normalized in CANCEL_WORDS:
        cancel_intent = "shopping.cancel" if write_previous_slots.get("shopping_flow") else "action.cancel"
        return _route_result(cancel_intent, slots=write_previous_slots)

    pending_shopping_intent = pending_shopping_flow_intent(text, write_previous_slots)
    if pending_shopping_intent:
        return _route_result(pending_shopping_intent, slots=write_previous_slots)

    # 새 응답은 구조화된 pending 슬롯을 우선 사용하고, 기존 문장 분석은 하위 호환으로 남깁니다.
    if isinstance(inventory_pending, dict):
        pending_type = inventory_pending.get("action")
        if pending_type == "add_many":
            if len(_extract_add_items(text)) > 1:
                return _route_result("inventory.pending_add_many", slots=previous_slots)
            if _is_quantity_only_list(text):
                return _route_result("inventory.pending_add_many_retry", slots=previous_slots)
        if pending_type == "add_storage" and _extract_storage(text):
            return _route_result("inventory.pending_add_storage", slots=previous_slots)
        if pending_type == "add_quantity" and (_extract_quantity(text) or _extract_storage(text)):
            return _route_result("inventory.pending_add", slots=previous_slots)
        if pending_type in {"consume_quantity", "consume_confirm"} and _extract_quantity(text):
            return _route_result("inventory.pending_consume", slots=previous_slots)
        if (
            pending_type in {"delete_quantity", "delete_confirm"}
            and (_extract_quantity(text) is not None or _is_all_quantity_request(text))
        ):
            return _route_result("inventory.pending_delete", slots=previous_slots)


    # 취소 직후 수량을 바꿔 다시 요청하면 직전 재료와 작업 종류를 한 번 이어받습니다.
    if isinstance(inventory_last_action, dict) and _extract_quantity(text):
        last_type = inventory_last_action.get("action")
        action_words = DELETE_WORDS if last_type == "delete_confirm" else CONSUME_WORDS
        if inventory_last_action.get("name") and ("처리" in normalized or any(word in normalized for word in action_words)):
            resumed_slots = {
                **previous_slots,
                "inventory_pending": {"action": last_type, "name": inventory_last_action["name"]},
                "inventory_last_action": None,
            }
            intent = "inventory.pending_delete" if last_type == "delete_confirm" else "inventory.pending_consume"
            return _route_result(intent, slots=resumed_slots)

    if legacy_pending_allowed and _pending_add_many_from_history(history):
        if len(_extract_add_items(text)) > 1:
            return _route_result("inventory.pending_add_many", slots=previous_slots)
        if _is_quantity_only_list(text):
            return _route_result("inventory.pending_add_many_retry", slots=previous_slots)
    if legacy_pending_allowed and _pending_add_storage_from_history(history) and _extract_storage(text):
        return _route_result("inventory.pending_add_storage", slots=previous_slots)
    if legacy_pending_allowed and _pending_add_from_history(history) and (_extract_quantity(text) or _extract_storage(text)):
        return _route_result("inventory.pending_add", slots=previous_slots)
    if legacy_pending_allowed and _pending_consume_from_history(history) and _extract_quantity(text):
        return _route_result("inventory.pending_consume", slots=previous_slots)

    write_route = _route_write_request(text, write_previous_intent, write_previous_slots, is_receipt_query)
    if write_route:
        return write_route

    # 읽기 요청은 LLM JSON 분류를 먼저 채택합니다.
    service = state.get("service")
    if service:
        route_payload = service._route_intent_payload_with_llm(text, history)
        route_payload = _inherit_route_context(route_payload, previous_intent, previous_slots)
        # 전담 Agent가 없는 명확한 일반 요리 질문은 잘못 분류된 LLM 결과만 보정합니다.
        if _is_food_general_query(text):
            route_payload = {**route_payload, "intent": "food.general", "confidence": 1.0, "tasks": []}
        # 메뉴 추천 표현은 일반 요리 지식 응답 대신 레시피 추천으로 보정합니다.
        elif _is_recipe_recommend_query(text):
            route_payload = {**route_payload, "intent": "recipe.recommend", "confidence": 1.0, "tasks": []}
        # 소비기한·임박 표현은 냉장고 목록이 아닌 임박 재료 조회로 보정합니다.
        elif _is_expiring_question(text):
            route_payload = {**route_payload, "intent": "inventory.expiring", "confidence": 1.0, "tasks": []}
        if route_payload.get("intent") == "shopping.compare":
            route_slots = route_payload.get("slots") or {}
            current_product = (
                route_slots.get("shopping_product")
                or route_slots.get("ingredient")
                or route_slots.get("keyword")
            )
            inherited_product = previous_slots.get("shopping_product") if previous_intent == "shopping.compare" else None
            if current_product or inherited_product:
                route_payload = {
                    **route_payload,
                    "slots": {**route_slots, "shopping_product": current_product or inherited_product},
                }
        if route_payload.get("confidence", 0.0) >= _LLM_ROUTE_CONFIDENCE:
            return _route_result(
                route_payload.get("intent", "general"),
                route_payload.get("confidence", 0.0),
                route_payload.get("slots", {}),
                route_payload.get("tasks", []),
            )

    return _route_read_fallback(text, history, previous_intent, previous_slots, is_receipt_query)

def inventory_agent_node(state: GraphState) -> dict:
    """재고 관리를 Inventory Agent로 위임합니다."""
    from ai.agents.inventory_agent.inventory_agent import run_inventory_agent
    
    intent = state.get("intent", "")
    if (intent.startswith("inventory.") or intent.startswith("action.")) and not state.get("user_id"):
        return _normalize_agent_result({"response_text": LOGIN_REQUIRED_REPLY}, inherited_slots=state.get("slots"))
        
    result = _run_agent_with_retry(
        lambda: run_inventory_agent(
            intent=intent,
            text=state["text"],
            history=state.get("history", []),
            db=state.get("db"),
            user_id=state.get("user_id"),
            slots=state.get("slots"),
        ),
        enabled=intent in {"inventory.list", "inventory.expiring"},
    )
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))


def _general_food_fallback(state: GraphState, query: str | None = None) -> dict:
    """도메인 Agent가 핵심 조건을 놓쳤을 때 일반 음식 Agent로 한 번만 보완합니다."""
    from ai.agents.general_food_agent import run_general_food

    result = _run_agent_with_retry(
        lambda: run_general_food(query or state["text"], history=state.get("history", []))
    )
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))


def guide_agent_node(state: GraphState) -> dict:
    """식재료 가이드 요청을 Guide Agent에 전달합니다."""
    query = _rewrite_guide_query(state["text"])
    slots = state.get("slots") or {}
    ingredient = slots.get("ingredient") or slots.get("keyword")
    guide_type = slots.get("guide_type")
    guide_labels = {
        "storage": "보관법",
        "washing": "세척법",
        "prep": "손질법",
        "freshness": "신선도 확인법",
    }
    normalized = _normalize_text(query)
    if ingredient and guide_type in guide_labels and (
        "물어보" in normalized
        or normalized.startswith("그럼")
        or (guide_type == "storage" and any(phrase in normalized for phrase in ("넣으면되", "넣어도되", "둬도되", "두면되", "보관해도되")))
    ):
        query = f"{ingredient} {guide_labels[guide_type]}"
    if ingredient and guide_type == "storage" and any(storage in normalized for storage in ("냉장", "냉동", "실온")):
        storage = next(storage for storage in ("냉장", "냉동", "실온") if storage in normalized)
        query = f"{ingredient} {storage} 보관법"

    result = _run_agent_with_retry(lambda: state["service"]._reply_guide(query))
    normalized_result = _normalize_agent_result(result, inherited_slots=state.get("slots"))
    if _should_use_food_fallback("guide", query, normalized_result.get("response_text", "")):
        return _general_food_fallback(state, query)
    return normalized_result


def recipe_agent_node(state: GraphState) -> dict:
    """레시피 검색/추천 요청을 Recipe Agent로 위임합니다."""
    query = state["text"]
    if state.get("intent") == "recipe.recommend" and not state.get("user_id"):
        return _normalize_agent_result(
            {"response_text": LOGIN_REQUIRED_REPLY},
            inherited_slots=state.get("slots"),
        )
    expiring_ingredients = (state.get("slots") or {}).get("expiring_ingredients") or []
    if state.get("intent") == "recipe.recommend" and expiring_ingredients:
        ingredient_names = ", ".join(expiring_ingredients)
        query = f"임박 재료({ingredient_names})를 우선 활용하고 현재 냉장고 재료를 고려한 레시피를 추천해줘"

    result = _run_agent_with_retry(
        lambda: run_recipe_agent(
            query,
            db=state.get("db"),
            user_id=state.get("user_id"),
            history=state.get("history", []),
            settings_obj=state.get("settings_obj"),
            intent=state.get("intent"),
        )
    )
    normalized_result = _normalize_agent_result(result, inherited_slots=state.get("slots"))
    if _should_use_food_fallback("recipe", state["text"], normalized_result.get("response_text", "")):
        return _general_food_fallback(state)
    if any(phrase in _normalize_text(state["text"]) for phrase in ("말고다른", "다른메뉴")):
        normalized_result["response_text"] = "이전에 본 메뉴와 겹치지 않는 다른 후보예요.\n" + normalized_result["response_text"]
    return normalized_result

def receipt_guide_node(state: GraphState) -> dict:
    """영수증 OCR 화면 이동 액션을 안내합니다."""
    result = {
        "response_text": "영수증은 파일 업로드가 필요해서 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요.",
        "actions": [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}],
    }
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))

def receipt_lookup_node(state: GraphState) -> dict:
    """영수증 내역/금액/품목 조회 화면 이동 액션을 안내합니다."""
    result = {
        "response_text": (
            "최근 영수증 내역과 금액, 품목은 영수증 화면에서 확인할 수 있어요. "
            "아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요."
        ),
        "actions": [{"label": "영수증 내역 보기", "url": "/receipt-ocr"}],
    }
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))

def shopping_agent_node(state: GraphState) -> dict:
    """장보기 관리를 Shopping Agent로 위임합니다."""
    from ai.agents.shopping_agent.shopping_agent import run_shopping_agent

    intent = state.get("intent", "")
    text = state["text"]
    if _is_shopping_price_explanation(text):
        intent = "shopping.price_help"
    elif _is_shopping_history_request(text):
        intent = "shopping.history"

    if intent != "shopping.price_help" and not state.get("user_id"):
        return _normalize_agent_result({"response_text": LOGIN_REQUIRED_REPLY}, inherited_slots=state.get("slots"))

    requested_quantity = _shopping_requested_quantity(text) if intent == "shopping.create" else None
    if intent == "shopping.create":
        text = _normalize_shopping_create_query(text)
    if intent == "shopping.delete_item":
        text = _normalize_shopping_delete_query(text)
    compare_text = _strip_shopping_compare_suffix(text)
    if intent == "shopping.compare" and not (state.get("slots") or {}).get("shopping_flow"):
        compare_text = (state.get("slots") or {}).get("shopping_product") or compare_text

    result = _run_agent_with_retry(
        lambda: run_shopping_agent(
            text=compare_text or text,
            intent=intent,
            history=state.get("history", []),
            slots=state.get("slots", {}),
            db=state.get("db"),
            user_id=state.get("user_id"),
        ),
        enabled=intent not in _SHOPPING_WRITE_INTENTS,
    )
    response_text = result.get("response_text", "") if isinstance(result, dict) else ""
    omitted_count = _truncated_shopping_count(state.get("history"))
    if intent == "shopping.current" and _is_shopping_show_all_request(state["text"]) and omitted_count and "목록이 없어요" in response_text:
        result = {
            "response_text": (
                f"앞선 응답에서 생략된 {omitted_count}개 품목은 대화 기록에 이름이 남아 있지 않아 바로 나열할 수 없어요. "
                "전체 품목은 장보기 목록 화면에서 확인해주세요."
            ),
            "actions": [{"label": "장보기 목록 보기", "url": "/shopping-list"}],
        }
    elif requested_quantity and "장보기 목록에 추가할까요" in response_text:
        item_name = response_text.split("를 장보기 목록에 추가할까요", 1)[0].strip()
        result["response_text"] = (
            f"{item_name} {requested_quantity}를 구매할 품목으로 장보기 목록에 추가할까요? "
            "현재 목록은 품목 단위로 저장되며 수량은 장보기 화면에서 조정할 수 있어요."
        )

    if intent == "shopping.compare":
        from ai.agents.shopping_agent.shopping_utils import extract_ingredient_names

        products = extract_ingredient_names(compare_text or text)
        if products:
            result["slots"] = {**(result.get("slots") or {}), "shopping_product": products[0]}
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))


def alarm_agent_node(state: GraphState) -> dict:
    """캘린더 및 알림 관리를 Alarm Agent로 위임합니다."""
    from ai.agents.alarm_agent import ALARM_AGENT_TOOLS
    from ai.agents.alarm_agent.alarm_agent import run as run_alarm_agent

    request = _parse_alarm_request(state["text"], state.get("intent", ""))
    agent_result = _run_agent_with_retry(
        lambda: run_alarm_agent(
            text_or_intent=state["text"],
            payload=request["payload"],
            intent=request["intent"],
            action=request["action"],
            confirmed=request["confirmed"],
            tools=ALARM_AGENT_TOOLS,
            context={"user_id": state.get("user_id"), "db": state.get("db")},
        ),
        enabled=not request["confirmed"] and not _is_alarm_write_query(state["text"]),
    )
    result = _alarm_result_to_state(agent_result)
    normalized_text = _normalize_text(state["text"])
    if result.get("response_text") == "등록된 알림 목록이에요." and "이번주" in normalized_text:
        keyword_match = re.search(r"이번\s*주\s*(.+?)\s*관련\s*알림", state["text"])
        keyword = keyword_match.group(1).strip() if keyword_match else "요청한 조건"
        result["response_text"] = (
            f"이번 주 {keyword} 관련 알림을 조회했어요. "
            "표시되는 항목이 없다면 해당 조건으로 등록된 알림이 없는 상태예요."
        )
    elif "등록할까요" in result.get("response_text", "") and not any(
        word in normalized_text for word in ("오전", "오후", "시", "분")
    ):
        result["response_text"] = result["response_text"].replace(
            "등록할까요", "시간이 지정되지 않아 기본 시간으로 등록할까요"
        )
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))

def general_food_agent_node(state: GraphState) -> dict:
    """일반 요리와 식재료 지식 질문을 General Food Agent에 전달합니다."""
    from ai.agents.general_food_agent import run_general_food

    result = _run_agent_with_retry(
        lambda: run_general_food(state["text"], history=state.get("history", []))
    )
    return _normalize_agent_result(result, inherited_slots=state.get("slots"))

def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문에는 고정 안내문만 반환합니다."""
    reply = (
        "확인 요청이 만료되었거나 이미 처리됐어요. 작업을 다시 요청해주세요."
        if state.get("intent") == "action.invalid"
        else GENERAL_REPLY
    )
    return _normalize_agent_result({"response_text": reply}, inherited_slots=state.get("slots"))

def multi_agent_node(state: GraphState) -> dict:
    """작업 목록을 순차 실행하고 일부 Agent 실패가 전체 응답을 막지 않게 합니다."""
    handlers = {
        "inventory_agent_node": inventory_agent_node,
        "guide_agent_node": guide_agent_node,
        "recipe_agent_node": recipe_agent_node,
        "receipt_guide_node": receipt_guide_node,
        "receipt_lookup_node": receipt_lookup_node,
        "shopping_agent_node": shopping_agent_node,
    }
    results = []
    completed_intents = []
    task_results = {}
    failed_intents = []

    tasks = list(state.get("tasks") or [])
    task_intents = [task.get("intent") for task in tasks]
    if "inventory.expiring" in task_intents and "recipe.recommend" in task_intents:
        expiring_index = task_intents.index("inventory.expiring")
        recipe_index = task_intents.index("recipe.recommend")
        if expiring_index > recipe_index:
            # 임박 재료 조회 결과가 필요한 레시피 추천보다 먼저 실행되도록 순서만 보정합니다.
            tasks.insert(recipe_index, tasks.pop(expiring_index))

    for task in tasks:
        intent = task.get("intent", "")
        task_state = {
            **state,
            "intent": intent,
            "text": task.get("text") or state["text"],
            "tasks": [],
        }
        # 임박 재료 조회 결과를 다음 레시피 추천 작업의 입력으로 전달합니다.
        if intent == "recipe.recommend" and "inventory.expiring" in completed_intents:
            expiring_slots = (task_results.get("inventory.expiring") or {}).get("slots") or {}
            expiring_names = expiring_slots.get("expiring_ingredients") or []
            task_state["slots"] = {**(task_state.get("slots") or {}), "expiring_ingredients": expiring_names}
            task_state["text"] = (
                f"{', '.join(expiring_names)}를 우선 활용하는 레시피를 추천해줘"
                if expiring_names else "냉장고 재료로 요리 추천해줘"
            )
        handler = handlers.get(route_intent(task_state))
        if not handler:
            failed_intents.append(intent)
            continue
        try:
            task_result = handler(task_state)
            if _agent_result_failed(task_result):
                failed_intents.append(intent)
            else:
                results.append(task_result)
                completed_intents.append(intent)
                task_results[intent] = task_result
        except Exception:
            logger.exception("Supervisor task failed: intent=%s", intent)
            failed_intents.append(intent)

    if failed_intents:
        results.append({"response_text": "일부 요청은 처리하지 못했어요. 잠시 후 다시 시도해주세요."})
    if not results:
        return general_node(state)

    result = _merge_agent_results(*results)
    result["slots"] = {
        **(result.get("slots") or {}),
        "completed_intents": completed_intents,
        "failed_intents": failed_intents,
    }
    return result


def route_intent(state: GraphState) -> str:
    """intent 값을 LangGraph 노드 이름으로 변환합니다."""
    intent = state.get("intent") or "general"
    if intent == "multi_agent":
        return "multi_agent_node"
    if intent.startswith("alarm."):
        return "alarm_agent_node"
    if intent.startswith("shopping."):
        return "shopping_agent_node"
    if intent.startswith("inventory.") or intent.startswith("action."):
        if intent == "action.invalid":
            return "general_node"
        if intent == "action.confirm":
            parts = state["text"].split(":")
            action = parts[1] if len(parts) >= 2 else ""
            if action in SHOPPING_CONFIRM_ACTIONS:
                return "shopping_agent_node"
            if action in _INVENTORY_CONFIRM_ACTIONS:
                return "inventory_agent_node"
            if action in _ALARM_CONFIRM_ACTIONS:
                return "alarm_agent_node"
            return "general_node"
        return "inventory_agent_node"
    routes = {
        "ingredient.guide": "guide_agent_node",
        "recipe.recommend": "recipe_agent_node",
        "recipe.search": "recipe_agent_node",
        "recipe.pairing": "recipe_agent_node",
        "receipt.lookup": "receipt_lookup_node",
        "receipt.guide": "receipt_guide_node",
        "food.general": "general_food_agent_node",
    }
    return routes.get(intent, "general_node")

workflow = StateGraph(GraphState)
workflow.add_node("router", router_node)
workflow.add_node("inventory_agent_node", inventory_agent_node)
workflow.add_node("multi_agent_node", multi_agent_node)
workflow.add_node("alarm_agent_node", alarm_agent_node)
workflow.add_node("shopping_agent_node", shopping_agent_node)
workflow.add_node("guide_agent_node", guide_agent_node)
workflow.add_node("recipe_agent_node", recipe_agent_node)
workflow.add_node("receipt_lookup_node", receipt_lookup_node)
workflow.add_node("receipt_guide_node", receipt_guide_node)
workflow.add_node("general_food_agent_node", general_food_agent_node)
workflow.add_node("general_node", general_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_intent)
for node_name in (
    "inventory_agent_node",
    "multi_agent_node",
    "alarm_agent_node",
    "shopping_agent_node",
    "guide_agent_node",
    "recipe_agent_node",
    "receipt_lookup_node",
    "receipt_guide_node",
    "general_food_agent_node",
    "general_node",
):
    workflow.add_edge(node_name, END)

supervisor_agent = workflow.compile()
