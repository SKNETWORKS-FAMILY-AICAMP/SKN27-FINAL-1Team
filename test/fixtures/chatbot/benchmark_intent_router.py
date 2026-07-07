import os
import sys
import time
import re

# 프로젝트 루트를 PATH에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from ai.agents.supervisor_agent.chat_graph import (
    CONFIRM_PREFIX, CANCEL_WORDS, CALENDAR_WORDS, ADD_WORDS, DELETE_WORDS, 
    CONSUME_WORDS, EXPIRING_WORDS, INVENTORY_LIST_WORDS
)
from ai.agents.supervisor_agent.chat_utils import _normalize_text
from app.backend.core.config import settings

# -----------------------------------------------------------------------------
# 1. 테스트 데이터셋 구성 (총 38개)
# -----------------------------------------------------------------------------
DATASET = [
    # mcp.inventory (추가/소비)
    {"text": "양파 2개 추가해", "expected": "mcp.inventory"},
    {"text": "냉장고에 감자 3개 넣어둬", "expected": "mcp.inventory"},
    {"text": "양상추 다 먹었어", "expected": "mcp.inventory"},
    {"text": "바베큐 소스도 다 먹음", "expected": "mcp.inventory"},
    {"text": "어제 소고기 구워먹었어", "expected": "mcp.inventory"},
    {"text": "방울토마토 추가", "expected": "mcp.inventory"},
    
    # mcp.delete (폐기)
    {"text": "상한 우유 버렸어", "expected": "mcp.delete"},
    {"text": "오래된 계란 쓰레기통에 버림", "expected": "mcp.delete"},
    {"text": "당근이 썩어서 폐기할게", "expected": "mcp.delete"},
    {"text": "파프리카 삭제해줘", "expected": "mcp.delete"},
    
    # mcp.calendar (일정)
    {"text": "내일 장보러 가야해", "expected": "mcp.calendar"},
    {"text": "모레 이마트 배송 일정 등록해", "expected": "mcp.calendar"},
    {"text": "이번주 주말에 마트 장보기", "expected": "mcp.calendar"},
    
    # inventory.list (재고 목록)
    {"text": "냉장고에 뭐 있어?", "expected": "inventory.list"},
    {"text": "지금 재료 남은거 좀 알려줘", "expected": "inventory.list"},
    {"text": "내 식재료 목록 보여줘", "expected": "inventory.list"},
    
    # inventory.expiring (유통기한 임박)
    {"text": "유통기한 임박한 거 찾아줘", "expected": "inventory.expiring"},
    {"text": "곧 상하는 거 뭐 있어?", "expected": "inventory.expiring"},
    {"text": "소비기한 며칠 남았지?", "expected": "inventory.expiring"},
    {"text": "빨리 먹어야 하는 재료 알려줘", "expected": "inventory.expiring"},
    
    # ingredient.guide (가이드)
    {"text": "대파 신선하게 보관하는 법 알려줘", "expected": "ingredient.guide"},
    {"text": "오이 세척법", "expected": "ingredient.guide"},
    {"text": "토마토 어떻게 손질해?", "expected": "ingredient.guide"},
    {"text": "가지 신선도 확인법", "expected": "ingredient.guide"},
    
    # recipe.search/recommend (레시피)
    {"text": "오늘 저녁은 소고기로 뭐 해먹지?", "expected": "recipe.recommend"},
    {"text": "이걸로 할 수 있는 요리 추천해봐", "expected": "recipe.recommend"},
    {"text": "김치찌개 레시피 알려줘", "expected": "recipe.search"},
    {"text": "15분 안에 만들 수 있는 반찬", "expected": "recipe.search"},
    
    # general (일반 대화)
    {"text": "안녕 반가워!", "expected": "general"},
    {"text": "너 이름이 뭐야?", "expected": "general"},
    {"text": "오늘 날씨 좋네", "expected": "general"},
    {"text": "넌 뭘 할 수 있어?", "expected": "general"},
    
    # mcp.confirm / cancel (상태 전환)
    {"text": "확인:add_ingredient:양파:2:냉장", "expected": "mcp.confirm"},
    {"text": "취소", "expected": "mcp.cancel"},
    
    # ---------------------------------------------------------
    # 🌶️ Wild / Edge Cases (사용자가 횡설수설하거나 혼동하기 쉬운 문장들)
    # ---------------------------------------------------------
    {"text": "아 냉장고 보니까 오이가 좀 상한 거 같기도 하고... 일단 빼놓을까? 아니야 그냥 냅둬", "expected": "general"}, 
    {"text": "유통기한 다 된 우유로 뭐 만들 수 있을까?", "expected": "recipe.recommend"}, 
    {"text": "저번에 양배추 다 먹었는데 이번 주말에 마트가서 또 사야겠다", "expected": "mcp.calendar"}, 
    {"text": "이 레시피 너무 어려운데 그냥 다 쓰레기통에 버릴까봐", "expected": "general"},
    {"text": "양파 샀는데 아 아니다 양파 말고 대파 샀어", "expected": "mcp.inventory"},
    {"text": "어제 먹다 남은 치킨 어디에 활용하지?", "expected": "recipe.recommend"},
    {"text": "방금 마트에서 삼겹살 샀는데 신선하게 보관하려면 어떡해?", "expected": "ingredient.guide"},
    {"text": "아까 오이 버렸는데 냉장고에 뭐 남았는지 좀 알려줄래?", "expected": "inventory.list"},
    {"text": "장보기 귀찮은데 내일로 일정 미뤄줘", "expected": "mcp.calendar"},
    {"text": "유통기한 지난 두부 폐기하지 말고 찌개에 넣을까", "expected": "recipe.recommend"},
]

# -----------------------------------------------------------------------------
# 2. 라우터 함수 정의
# -----------------------------------------------------------------------------

def rule_based_router(text: str) -> str:
    """순수 룰 베이스 라우팅"""
    normalized = _normalize_text(text)
    
    if normalized.startswith(CONFIRM_PREFIX):
        return "mcp.confirm"
    if normalized in CANCEL_WORDS:
        return "mcp.cancel"
        
    if any(word in normalized for word in DELETE_WORDS):
        return "mcp.delete"
    if any(word in normalized for word in CONSUME_WORDS):
        return "mcp.inventory"
    if any(word in normalized for word in CALENDAR_WORDS):
        return "mcp.calendar"
    if any(word in normalized for word in ADD_WORDS):
        return "mcp.inventory"
    if any(word in normalized for word in EXPIRING_WORDS):
        return "inventory.expiring"
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
        return "inventory.list"
        
    if any(word in normalized for word in ("유통기한", "소비기한", "상하는", "기한", "빨리", "먼저")):
        return "inventory.expiring"
    if any(word in normalized for word in ("분", "시간", "오래")):
        return "recipe.search"
    guide_words = ("보관", "세척", "씻", "손질", "신선", "가이드", "어떡", "남은")
    if any(word in normalized for word in guide_words):
        return "ingredient.guide"
        
    return "general"

llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_MODEL, temperature=0.0)

def llm_only_router(text: str) -> str:
    """오직 프롬프트로만 의도를 분류하는 순수 LLM 라우터"""
    system_prompt = """다음 사용자의 입력을 분석하여 가장 알맞은 의도(Intent) 하나만 답변해. 
답변은 아래 목록 중 정확히 하나여야 해.

- mcp.inventory: 추가, 소비
- mcp.delete: 폐기, 버림
- mcp.calendar: 일정, 장보기
- inventory.list: 조회, 목록
- inventory.expiring: 임박, 상하는, 기한
- ingredient.guide: 보관, 세척, 손질, 신선도 질문 (남은 재료 보관 질문 포함)
- recipe.search: 레시피 검색, 시간 기반
- recipe.recommend: 메뉴 추천, 남은 재료 요리 추천
- mcp.confirm: 확인
- mcp.cancel: 취소
- general: 인사, 잡담
"""
    try:
        res = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=text)
        ])
        ans = res.content.strip()
        for valid in ["mcp.inventory", "mcp.delete", "mcp.calendar", "inventory.list", 
                      "inventory.expiring", "ingredient.guide", "recipe.search", 
                      "recipe.recommend", "mcp.confirm", "mcp.cancel", "general"]:
            if valid in ans:
                return valid
        return "general"
    except Exception as e:
        return "general"

def hybrid_router(text: str) -> str:
    """현재 프로덕션 라우터 방식 (Rule-base -> LLM Fallback)"""
    # 1. 룰 베이스 통과
    normalized = _normalize_text(text)
    
    if normalized.startswith(CONFIRM_PREFIX): return "mcp.confirm"
    if normalized in CANCEL_WORDS: return "mcp.cancel"
    if any(word in normalized for word in DELETE_WORDS): return "mcp.delete"
    if any(word in normalized for word in CONSUME_WORDS): return "mcp.inventory"
    if any(word in normalized for word in CALENDAR_WORDS): return "mcp.calendar"
    if any(word in normalized for word in ADD_WORDS): return "mcp.inventory"
    if any(word in normalized for word in EXPIRING_WORDS): return "inventory.expiring"
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS): return "inventory.list"
    
    # 2. Fallback 으로 LLM 내부 키워드 통과
    if any(word in normalized for word in ("유통기한", "소비기한", "상하는", "기한", "빨리", "먼저")):
        return "inventory.expiring"
    if any(word in normalized for word in ("분", "시간", "오래")):
        return "recipe.search"
    guide_words = ("보관", "세척", "씻", "손질", "신선", "가이드", "어떡", "남은")
    if any(word in normalized for word in guide_words):
        return "ingredient.guide"
        
    # 3. 최후의 LLM 호출
    return llm_only_router(text)


# -----------------------------------------------------------------------------
# 3. 벤치마크 루프
# -----------------------------------------------------------------------------
def run_benchmark(name: str, router_func) -> dict:
    correct = 0
    total = len(DATASET)
    start_time = time.time()
    
    print(f"\\n--- Running Benchmark: {name} ---")
    for item in DATASET:
        text = item["text"]
        expected = item["expected"]
        
        pred = router_func(text)
        is_match = (pred == expected)
        
        if is_match:
            correct += 1
        else:
            print(f"[FAIL] Text: '{text}' | Expected: {expected} | Pred: {pred}")
            
    end_time = time.time()
    latency = (end_time - start_time) / total
    acc = (correct / total) * 100
    
    print(f"Result -> Accuracy: {acc:.1f}% ({correct}/{total}), Avg Latency: {latency:.4f} sec/req")
    return {"accuracy": acc, "latency": latency}

if __name__ == "__main__":
    print("Starting Intent Router Benchmarks...")
    
    if not settings.OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY is not set.")
        sys.exit(1)
        
    results = {}
    
    results["Rule-based"] = run_benchmark("Rule-based Only", rule_based_router)
    results["LLM-only"] = run_benchmark("LLM Only", llm_only_router)
    results["Hybrid"] = run_benchmark("Hybrid (Current)", hybrid_router)
    
    print("\\n================ FINAL REPORT ================")
    for k, v in results.items():
        print(f"[{k}] Accuracy: {v['accuracy']:.1f}%, Latency: {v['latency']:.4f} sec")
    print("==============================================")
