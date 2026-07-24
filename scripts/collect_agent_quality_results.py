"""고난도 평가 데이터셋으로 도메인 에이전트를 실행하고 응답을 JSONL로 저장합니다."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backend.db.session import SessionLocal
from ai.agents.supervisor_agent.supervisor_agent import (
    alarm_agent_node,
    general_food_agent_node,
    guide_agent_node,
    inventory_agent_node,
    recipe_agent_node,
    shopping_agent_node,
)
from ai.agents.supervisor_agent.supervisor_service import supervisor_service


DATASET_PATH = Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl")
AGENT_NODES = {
    "inventory": inventory_agent_node,
    "guide": guide_agent_node,
    "recipe": recipe_agent_node,
    "shopping": shopping_agent_node,
    "alarm": alarm_agent_node,
    "general_food": general_food_agent_node,
}


def load_cases(agent: str | None) -> list[dict]:
    """선택한 에이전트의 고난도 평가 케이스만 읽습니다."""
    cases = [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [case for case in cases if agent is None or case["agent"] == agent]


def infer_intent(case: dict) -> str:
    """평가 문장을 안전한 조회 또는 미리보기 intent로 변환합니다."""
    text = case["message"].replace(" ", "")
    agent = case["agent"]
    if agent == "inventory":
        if "소비기한" in text or "빨리먹" in text:
            return "inventory.expiring"
        if "삭제" in text or "폐기" in text:
            return "inventory.delete"
        if "뭐가있" in text:
            return "inventory.list"
        return "inventory.action"
    if agent == "recipe":
        if "먹기좋" in text or "어울" in text:
            return "recipe.pairing"
        if "레시피" in text:
            return "recipe.search"
        return "recipe.recommend"
    if agent == "shopping":
        if "가격" in text or "싼" in text or "비싸" in text:
            return "shopping.compare"
        if "넣어" in text:
            return "shopping.create"
        if "빼줘" in text:
            return "shopping.delete_item"
        return "shopping.current"
    if agent == "alarm":
        return "alarm.calendar" if "일정" in text else "alarm.notification"
    return {"guide": "ingredient.guide", "general_food": "food.general"}[agent]


def run_case(case: dict, db, user_id: int) -> dict:
    """확인 명령 없이 단일 에이전트의 미리보기 응답을 수집합니다."""
    node = AGENT_NODES[case["agent"]]
    state = {
        "text": case["message"],
        "history": case["history"],
        "intent": infer_intent(case),
        "db": db,
        "user_id": user_id,
        "slots": {},
        "service": supervisor_service,
    }
    try:
        result = node(state)
    except Exception as error:
        # 실행 환경 오류를 품질 점수와 구분하기 위해 결과에 기록합니다.
        result = {"response_text": "", "error": f"{type(error).__name__}: {error}"}
    return {
        "id": case["id"],
        "agent": case["agent"],
        "intent": state["intent"],
        "response_text": result.get("response_text", ""),
        "actions": result.get("actions", []),
        "sources": result.get("sources", []),
        "slots": result.get("slots", {}),
        "error": result.get("error"),
    }


def main() -> None:
    """개발 DB에서 도메인 에이전트의 실제 응답을 수집합니다."""
    parser = argparse.ArgumentParser(description="도메인 에이전트 평가 응답 수집")
    parser.add_argument("--user-id", type=int, required=True, help="평가용 사용자 ID")
    parser.add_argument("--agent", choices=tuple(AGENT_NODES), help="특정 에이전트만 실행")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/domain-agent-results.jsonl"))
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = [run_case(case, db, args.user_id) for case in load_cases(args.agent)]
    finally:
        # 평가 중에는 확인 명령을 보내지 않으며 세션도 롤백으로 정리합니다.
        db.rollback()
        db.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(f"응답 {len(rows)}건을 {args.output}에 저장했습니다.")


if __name__ == "__main__":
    main()
