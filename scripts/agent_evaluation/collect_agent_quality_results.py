"""고난도 평가 데이터셋으로 도메인 에이전트를 실행하고 응답을 JSONL로 저장합니다."""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


DATASET_PATHS = (
    Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl"),
    Path("test/fixtures/agent_evaluation/agent_regression_cases.jsonl"),
)
DEFAULT_PROFILE_PATH = Path("test/fixtures/agent_evaluation/evaluation_profile.json")

AGENT_NODES = {
    "inventory": inventory_agent_node,
    "guide": guide_agent_node,
    "recipe": recipe_agent_node,
    "shopping": shopping_agent_node,
    "alarm": alarm_agent_node,
    "general_food": general_food_agent_node,
}


def load_profile(path: Path) -> dict:
    """반복 평가에 사용할 기준 사용자와 환경 정보를 읽습니다."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_cases(agent: str | None, regression_only: bool = False) -> list[dict]:
    """고난도 평가셋과 실제 실패 회귀셋을 함께 읽습니다."""
    dataset_paths = DATASET_PATHS[1:] if regression_only else DATASET_PATHS
    cases = [
        json.loads(line)
        for dataset_path in dataset_paths
        for line in dataset_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    return [case for case in cases if agent is None or case["agent"] == agent]

def _latest_bot_context(history: list[dict]) -> tuple[str, dict]:
    """평가 케이스의 마지막 봇 메시지에서 대기 문맥과 슬롯을 복원합니다."""
    for message in reversed(history or []):
        if message.get("role") == "bot":
            return message.get("text", ""), message.get("slots") if isinstance(message.get("slots"), dict) else {}
    return "", {}


def infer_intent(case: dict) -> str:
    """평가 문장을 해당 도메인의 조회 또는 미리보기 intent로 변환합니다."""
    text = case["message"].replace(" ", "")
    agent = case["agent"]
    previous_text, _ = _latest_bot_context(case.get("history", []))
    previous_normalized = previous_text.replace(" ", "")
    if agent == "inventory":
        if "소비기한" in text or "빨리먹" in text:
            return "inventory.expiring"
        if "보관위치" in text and any(storage in text for storage in ("냉장", "냉동", "실온")):
            return "inventory.storage_change"
        if "삭제" in text or "폐기" in text or "버릴" in text:
            return "inventory.delete"
        if "뭐가있" in text or "남아있" in text or "재고" in text:
            return "inventory.list"
        if "어디에보관" in previous_normalized and any(storage in text for storage in ("냉장", "냉동", "실온")):
            return "inventory.pending_add_storage"
        if "몇개추가" in previous_normalized and any(char.isdigit() for char in text):
            return "inventory.pending_add"
        if "몇개소비" in previous_normalized and any(char.isdigit() for char in text):
            return "inventory.pending_consume"
        if "몇개폐기" in previous_normalized and any(char.isdigit() for char in text):
            return "inventory.pending_delete"
        return "inventory.action"
    if agent == "recipe":
        if "먹기좋" in text or "어울" in text:
            return "recipe.pairing"
        if "레시피" in text and "추천" not in text:
            return "recipe.search"
        return "recipe.recommend"
    if agent == "shopping":
        if "가격" in text or "싼" in text or "비싸" in text:
            return "shopping.compare"
        if "넣어" in text or "추가" in text:
            return "shopping.create"
        if "빼줘" in text or "삭제" in text:
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
        # 평가 픽스처의 JSON 메시지를 실제 채팅 객체와 같은 속성 접근 형태로 변환합니다.
        "history": [SimpleNamespace(**message) if isinstance(message, dict) else message for message in case["history"]],
        "intent": infer_intent(case),
        "db": db,
        "user_id": user_id,
        "slots": _latest_bot_context(case.get("history", []))[1],
        "service": supervisor_service,
    }
    try:
        result = node(state)
    except Exception as error:
        # 인프라 오류를 품질 실패 점수와 구분하기 위해 결과에 기록합니다.
        result = {"response_text": "", "error": f"{type(error).__name__}: {error}"}
    ui = result.get("ui") if isinstance(result.get("ui"), dict) else {}
    return {
        "id": case["id"],
        "agent": case["agent"],
        "intent": state["intent"],
        "response_text": result.get("response_text", ""),
        "actions": result.get("actions") or ui.get("actions", []),
        "sources": result.get("sources") or ui.get("sources", []),
        "slots": result.get("slots", {}),
        "error": result.get("error"),
    }


def main() -> None:
    """개발 DB에서 도메인 에이전트의 실제 응답을 수집합니다."""
    parser = argparse.ArgumentParser(description="도메인 에이전트 평가 응답 수집")
    parser.add_argument("--user-id", type=int, help="평가용 사용자 ID. 생략하면 평가 프로필 값을 사용")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH, help="평가 환경 프로필 JSON")
    parser.add_argument("--agent", choices=tuple(AGENT_NODES), help="특정 에이전트만 실행")
    parser.add_argument("--regression-only", action="store_true", help="실패 회귀셋만 실행")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/domain-agent-results.jsonl"))
    args = parser.parse_args()

    profile = load_profile(args.profile)
    user_id = args.user_id or profile.get("user_id")
    if not isinstance(user_id, int):
        parser.error("평가용 사용자 ID가 필요합니다.")

    db = SessionLocal()
    try:
        rows = [run_case(case, db, user_id) for case in load_cases(args.agent, args.regression_only)]
    finally:
        # 평가 중에는 확인 명령을 보내지 않으며 세션도 롤백으로 정리합니다.
        db.rollback()
        db.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    print(f"프로필 {profile.get('profile', 'custom')} 기준 응답 {len(rows)}건을 {args.output}에 저장했습니다.")


if __name__ == "__main__":
    main()
