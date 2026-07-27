"""에이전트 공통 평가 데이터셋의 구조와 분포를 검증합니다."""

import json
from collections import Counter
from pathlib import Path

from scripts.evaluate_supervisor_routing import classify_failure


# 에이전트별 최소 비교 단위가 흔들리지 않도록 목표 분포를 고정합니다.
EXPECTED_AGENT_COUNTS = {"supervisor": 20}
EXPECTED_SPLIT_COUNTS = {"dev": 14, "holdout": 6}
EXPECTED_DEV_AGENT_COUNTS = {"supervisor": 14}
DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_evaluation"
    / "agent_eval_cases.jsonl"
)


def _load_cases() -> list[dict]:
    """JSONL 형식의 에이전트 평가 케이스를 읽어 반환합니다."""
    return [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()]


def test_agent_evaluation_dataset_has_balanced_agent_counts():
    """도메인별 평가 케이스 수가 합의한 균형 분포와 같은지 확인합니다."""
    cases = _load_cases()

    assert len(cases) == 20
    assert Counter(case["agent"] for case in cases) == EXPECTED_AGENT_COUNTS
    assert Counter(case["split"] for case in cases) == EXPECTED_SPLIT_COUNTS
    assert Counter(case["agent"] for case in cases if case["split"] == "dev") == EXPECTED_DEV_AGENT_COUNTS


def test_agent_evaluation_dataset_has_required_contract_fields():
    """각 평가 케이스가 실행기에서 사용할 공통 계약 필드를 갖는지 확인합니다."""
    cases = _load_cases()

    assert len({case["id"] for case in cases}) == len(cases)

    # 같은 Agent 안에서는 질문과 이전 대화 조합이 중복되지 않아야 평가 건수를 부풀리지 않습니다.
    for agent in EXPECTED_AGENT_COUNTS:
        agent_cases = [case for case in cases if case["agent"] == agent]
        conversations = {
            (case["message"], json.dumps(case["history"], ensure_ascii=False, sort_keys=True))
            for case in agent_cases
        }
        assert len(conversations) == len(agent_cases)
    for case in cases:
        expected = case["expected"]

        assert case["message"]
        assert "???" not in case["message"]
        assert isinstance(case["history"], list)
        assert case["difficulty"] == "hard"
        assert case["scenario"]
        assert expected["intent"]
        assert isinstance(expected["requires_confirmation"], bool)
        assert isinstance(expected["required_slots"], list)
        assert expected["acceptance"]
        if expected["intent"] == "multi_agent":
            # 다중의도 요청은 두 개 이상의 작업 intent를 명시해야 합니다.
            assert len(expected["tasks"]) >= 2
            assert all(task["intent"] for task in expected["tasks"])


def test_supervisor_failure_types_distinguish_wrong_agent_from_detail_mismatch():
    """라우팅 실패는 담당 Agent 오류와 세부 intent 오류를 분리해야 합니다."""
    assert classify_failure("ingredient.guide", "food.general") == "wrong_agent"
    assert classify_failure("shopping.price_help", "shopping.compare") == "intent_detail_mismatch"
    assert classify_failure("inventory.list", "inventory.list") == "passed"