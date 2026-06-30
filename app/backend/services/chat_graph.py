from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.backend.core.config import settings
from app.backend.mcp_server.calendar_tools import CALENDAR_TOOLS
from app.backend.mcp_server.inventory_tools import INVENTORY_TOOLS
from app.backend.schemas.chat_state import GraphState

LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "요리나 식재료 관련 질문을 물어봐 주세요.\n예: 양파 보관법, 감자튀김 에어프라이기 시간, 두부 레시피"


def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    text = state["text"]
    intent = state["service"]._route_intent_with_llm(text, state.get("history", []))
    normalized = text.replace(" ", "").lower()

    inventory_action_words = ("먹었어", "다썼어", "다먹었어", "버렸어", "소비했", "사용했", "썼어", "추가해줘", "등록해줘", "넣었어", "넣어줘")
    if any(word in normalized for word in ("일정", "캘린더")):
        intent = "mcp.calendar"
    elif any(word in normalized for word in inventory_action_words):
        intent = "mcp.inventory"

    return {"intent": intent}


def mcp_agent_node(state: GraphState) -> dict:
    """LLM tool call을 받아 현재 지원하는 MCP성 동작만 실행합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    messages = state.get("messages") or [HumanMessage(content=state["text"])]
    tools_by_intent = {"mcp.inventory": INVENTORY_TOOLS, "mcp.calendar": CALENDAR_TOOLS}
    tools = tools_by_intent.get(state["intent"], [])

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    response = llm.bind_tools(tools).invoke(messages)

    if not response.tool_calls:
        return {"response_text": response.content, "messages": messages + [response]}

    tool_call = response.tool_calls[0]
    func_name = tool_call["name"]
    args = tool_call["args"]

    if func_name == "consume_ingredient":
        from app.backend.services.inventory_service.inventory_service import inventory_service

        reply = inventory_service.consume_ingredient_by_name(
            state["db"],
            state["user_id"],
            args.get("ingredient_name", ""),
            args.get("quantity", 1.0),
        )
        return {"response_text": reply, "messages": messages + [response]}

    pending_replies = {
        "add_ingredient": "재료 추가는 아직 챗봇에서 준비 중이에요. 지금은 냉장고 화면의 재료 추가 버튼으로 등록해주세요.",
        "add_calendar_event": "캘린더 등록은 아직 챗봇에서 준비 중이에요. 지금은 캘린더 화면에서 직접 등록해주세요.",
    }
    return {"response_text": pending_replies.get(func_name, "아직 지원하지 않는 챗봇 작업이에요."), "messages": messages + [response]}


def inventory_list_node(state: GraphState) -> dict:
    """로그인 사용자의 냉장고 재료 목록을 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    return {"response_text": state["service"]._reply_inventory_list(state["db"], state["user_id"])}


def inventory_expiring_node(state: GraphState) -> dict:
    """로그인 사용자의 소비기한 임박 재료를 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    return {"response_text": state["service"]._reply_expiring_items(state["db"], state["user_id"], state["text"])}


def ingredient_guide_node(state: GraphState) -> dict:
    """식재료 보관/손질 가이드를 안내합니다."""
    reply, sources = state["service"]._reply_guide(state["text"])
    return {"response_text": reply, "sources": sources}


def recipe_recommend_node(state: GraphState) -> dict:
    """냉장고 기반 또는 재료 기반 레시피 추천을 안내합니다."""
    svc = state["service"]
    if svc._requires_login("recipe.recommend", state["text"]) and not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    reply, actions = svc._reply_recipe_recommend(state["db"], state["user_id"], state["text"], state.get("history", []), state.get("settings_obj"))
    return {"response_text": reply, "actions": actions}


def recipe_search_node(state: GraphState) -> dict:
    """레시피 검색 결과를 안내합니다."""
    reply, actions, sources = state["service"]._reply_recipe_search(state["db"], state["text"])
    return {"response_text": reply, "actions": actions, "sources": sources}


def receipt_guide_node(state: GraphState) -> dict:
    """영수증 OCR 화면 이동 액션을 안내합니다."""
    return {
        "response_text": "영수증은 파일 업로드가 필요해서 상단 메뉴나 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요.",
        "actions": [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}],
    }


def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문에 기본 안내를 반환합니다."""
    return {"response_text": GENERAL_REPLY}


def route_intent(state: GraphState) -> str:
    """intent 값을 LangGraph 노드 이름으로 변환합니다."""
    intent = state.get("intent") or "general"
    if intent.startswith("mcp."):
        return "mcp_agent_node"
    routes = {
        "inventory.list": "inventory_list_node",
        "inventory.expiring": "inventory_expiring_node",
        "ingredient.guide": "ingredient_guide_node",
        "recipe.recommend": "recipe_recommend_node",
        "recipe.search": "recipe_search_node",
        "receipt.guide": "receipt_guide_node",
    }
    return routes.get(intent, "general_node")


workflow = StateGraph(GraphState)
workflow.add_node("router", router_node)
workflow.add_node("mcp_agent_node", mcp_agent_node)
workflow.add_node("inventory_list_node", inventory_list_node)
workflow.add_node("inventory_expiring_node", inventory_expiring_node)
workflow.add_node("ingredient_guide_node", ingredient_guide_node)
workflow.add_node("recipe_recommend_node", recipe_recommend_node)
workflow.add_node("recipe_search_node", recipe_search_node)
workflow.add_node("receipt_guide_node", receipt_guide_node)
workflow.add_node("general_node", general_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_intent)
for node_name in (
    "mcp_agent_node",
    "inventory_list_node",
    "inventory_expiring_node",
    "ingredient_guide_node",
    "recipe_recommend_node",
    "recipe_search_node",
    "receipt_guide_node",
    "general_node",
):
    workflow.add_edge(node_name, END)

chat_graph = workflow.compile()
