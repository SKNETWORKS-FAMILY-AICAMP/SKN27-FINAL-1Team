"""도메인 에이전트 응답 품질 평가 데이터셋의 최소 구조를 검증합니다."""

import json
from collections import Counter
from pathlib import Path

from scripts.evaluate_agent_quality import build_report


DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "agent_evaluation"
    / "domain_agent_quality_cases.jsonl"
)
EXPECTED_AGENT_COUNTS = {
    "inventory": 8,
    "guide": 8,
    "recipe": 8,
    "shopping": 8,
    "alarm": 8,
    "general_food": 8,
}


def _load_cases() -> list[dict]:
    """고난도 도메인 에이전트 평가 케이스를 읽습니다."""
    return [json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_domain_agent_quality_dataset_is_balanced_and_hard():
    """모든 도메인 에이전트가 같은 수의 고난도 질문을 받는지 확인합니다."""
    cases = _load_cases()

    assert len(cases) == 48
    assert Counter(case["agent"] for case in cases) == EXPECTED_AGENT_COUNTS
    assert all(case["difficulty"] == "hard" for case in cases)
    assert len({case["id"] for case in cases}) == len(cases)


def test_domain_agent_quality_dataset_has_response_quality_criteria():
    """각 케이스가 필수 정보와 금지 표현을 함께 정의하는지 검증합니다."""
    for case in _load_cases():
        acceptance = case["expected"]["acceptance"]

        assert case["message"]
        assert case["expected"]["scenario"]
        assert isinstance(case["history"], list)
        assert isinstance(acceptance["must_contain_any"], list)
        assert isinstance(acceptance["forbidden_patterns"], list)
        assert acceptance["minimum_length"] >= 20


def test_domain_agent_quality_report_rejects_wrong_domain_response():
    """필수 정보 누락과 금지 표현이 있는 응답을 실패로 계산하는지 확인합니다."""
    cases = [
        {
            "id": "guide-case",
            "agent": "guide",
            "expected": {
                "acceptance": {
                    "must_contain_any": ["양파"],
                    "must_contain_all": ["보관"],
                    "forbidden_patterns": ["현재 냉장고"],
                    "minimum_length": 20,
                }
            },
        },
        {
            "id": "shopping-case",
            "agent": "shopping",
            "expected": {
                "acceptance": {
                    "must_contain_any": ["가격"],
                    "forbidden_patterns": [],
                    "minimum_length": 20,
                }
            },
        },
    ]
    results = [
        {"id": "guide-case", "response_text": "현재 냉장고에 양파가 있어요."},
        {"id": "shopping-case", "response_text": "가격 비교 결과예요. 판매처와 용량을 확인한 뒤 가격 정보를 안내할게요."},
    ]

    report = build_report(cases, results)

    assert report["passed"] == 1
    assert report["by_agent"]["guide"]["accuracy"] == 0.0
    assert report["by_agent"]["shopping"]["accuracy"] == 1.0
