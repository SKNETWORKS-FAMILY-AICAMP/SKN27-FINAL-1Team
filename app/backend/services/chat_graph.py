from typing import Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.backend.schemas.chat_state import GraphState
from app.backend.core.config import app_settings
from app.backend.mcp_server.inventory_tools import INVENTORY_TOOLS
from app.backend.mcp_server.calendar_tools import CALENDAR_TOOLS

# -------------------------------------------------------------------------
# Nodes
# -------------------------------------------------------------------------

def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 의도(intent)를 파악합니다."""
    text = state["text"]
    svc = state["service"]
    history = state.get("history", [])
    
    # 기존 LLM 기반 라우터 실행
    intent = svc._route_intent_with_llm(text, history)
    
    # MCP 관련 특수 의도 오버라이드 (정규식 기반)
    normalized = text.replace(" ", "").lower()
    if any(word in normalized for word in ("먹었어", "다썼어", "다먹었어", "버렸어", "소비")):
        intent = "mcp.inventory"
    elif any(word in normalized for word in ("일정", "캘린더", "등록해줘")):
        intent = "mcp.calendar"
        
    return {"intent": intent}

def mcp_agent_node(state: GraphState) -> dict:
    """MCP 도구(재료 소비, 추가, 캘린더 등록 등)를 LLM과 연동하여 호출하는 노드입니다."""
    messages = state.get("messages", [])
    if not messages:
        messages = [HumanMessage(content=state["text"])]
        
    # intent에 따라 사용할 도구를 선택합니다.
    tools = []
    if state["intent"] == "mcp.inventory":
        tools = INVENTORY_TOOLS
    elif state["intent"] == "mcp.calendar":
        tools = CALENDAR_TOOLS
        
    llm = ChatOpenAI(
        model=app_settings.OPENAI_MODEL, 
        api_key=app_settings.OPENAI_API_KEY, 
        temperature=0.0
    )
    llm_with_tools = llm.bind_tools(tools)
    
    # LLM 호출
    response = llm_with_tools.invoke(messages)
    
    # 도구 호출(Tool Call)이 발생했는지 확인
    if response.tool_calls:
        # (주의: 실제 프로덕션에서는 ToolNode를 추가로 두어 실제 함수를 실행해야 함)
        # 지금은 단순히 챗봇이 "몇 개를 소비하셨나요?" 라고 되묻거나 
        # "함수가 호출되었습니다" 라는 응답을 생성하는 역할만 수행하도록 모의 처리.
        # 실제로는 여기서 파라미터가 다 찼다면 도구를 실행하고 결과를 받아와야 합니다.
        if len(response.tool_calls) > 0:
            tool_call = response.tool_calls[0]
            # 인자가 부족해서 LLM이 되묻는 경우 등은 response.content 에 담겨옵니다.
            # 만약 인자가 완벽하다면 여기서 수동으로 도구를 실행해 볼 수도 있습니다.
            func_name = tool_call["name"]
            args = tool_call["args"]
            return {"response_text": f"🔧 [MCP Tool] {func_name} 호출 준비 완료: {args}"}
            
    # 일반 텍스트 응답인 경우 (예: "몇 개 소비하셨을까요?")
    return {"response_text": response.content, "messages": messages + [response]}

# -------------------------------------------------------------------------
# Edge Routing Function
# -------------------------------------------------------------------------
def inventory_list_node(state: GraphState) -> dict:
    if not state["user_id"]:
        return {"response_text": "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."}
    svc = state["service"]
    reply = svc._reply_inventory_list(state["db"], state["user_id"])
    return {"response_text": reply}

def inventory_expiring_node(state: GraphState) -> dict:
    if not state["user_id"]:
        return {"response_text": "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."}
    svc = state["service"]
    reply = svc._reply_expiring_items(state["db"], state["user_id"], state["text"])
    return {"response_text": reply}

def ingredient_guide_node(state: GraphState) -> dict:
    svc = state["service"]
    reply, sources = svc._reply_guide(state["text"])
    return {"response_text": reply, "sources": sources}

def recipe_recommend_node(state: GraphState) -> dict:
    svc = state["service"]
    if svc._requires_login("recipe.recommend", state["text"]) and not state["user_id"]:
        return {"response_text": "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."}
    reply, actions = svc._reply_recipe_recommend(state["db"], state["user_id"], state["text"], state.get("history", []), state.get("settings_obj"))
    return {"response_text": reply, "actions": actions}

def recipe_search_node(state: GraphState) -> dict:
    svc = state["service"]
    reply, actions, sources = svc._reply_recipe_search(state["db"], state["text"])
    return {"response_text": reply, "actions": actions, "sources": sources}

def receipt_guide_node(state: GraphState) -> dict:
    reply = "영수증은 파일 업로드가 필요해서 상단 메뉴나 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요."
    actions = [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}]
    return {"response_text": reply, "actions": actions}

def general_node(state: GraphState) -> dict:
    return {"response_text": "요리나 식재료 관련 질문을 물어봐 주세요.\n예: 양파 보관법, 감자튀김 에어프라이기 시간, 두부 레시피"}

# -------------------------------------------------------------------------
# Graph Compilation
# -------------------------------------------------------------------------
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

def route_intent(state: GraphState) -> str:
    intent = state.get("intent", "general")
    if intent.startswith("mcp."):
        return "mcp_agent_node"
    if intent == "inventory.list":
        return "inventory_list_node"
    if intent == "inventory.expiring":
        return "inventory_expiring_node"
    if intent == "ingredient.guide":
        return "ingredient_guide_node"
    if intent == "recipe.recommend":
        return "recipe_recommend_node"
    if intent == "recipe.search":
        return "recipe_search_node"
    if intent == "receipt.guide":
        return "receipt_guide_node"
    return "general_node"

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_intent)
workflow.add_edge("mcp_agent_node", END)
workflow.add_edge("inventory_list_node", END)
workflow.add_edge("inventory_expiring_node", END)
workflow.add_edge("ingredient_guide_node", END)
workflow.add_edge("recipe_recommend_node", END)
workflow.add_edge("recipe_search_node", END)
workflow.add_edge("receipt_guide_node", END)
workflow.add_edge("general_node", END)

chat_graph = workflow.compile()
