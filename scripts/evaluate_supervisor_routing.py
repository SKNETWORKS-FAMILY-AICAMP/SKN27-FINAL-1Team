"""Supervisor 라우팅 평가셋을 실행하고 intent·에이전트 정확도를 기록합니다."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# 스크립트를 직접 실행해도 프로젝트 루트의 ai 패키지를 찾도록 경로를 보정합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai.agents.supervisor_agent.supervisor_agent import router_node
from ai.agents.supervisor_agent.supervisor_service import supervisor_service


DATASET_PATH = Path("test/fixtures/agent_evaluation/agent_eval_cases.jsonl")
INTENT_AGENT_PREFIXES = {
    "inventory.": "inventory",
    "ingredient.": "guide",
    "recipe.": "recipe",
    "shopping.": "shopping",
    "alarm.": "alarm",
    "food.general": "general_food",
    "multi_agent": "supervisor",
}


def load_cases(split: str) -> list[dict]:
    """선택한 데이터 분할에 해당하는 평가 케이스를 읽어옵니다."""
    rows = (json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines())
    return [row for row in rows if split == "all" or row["split"] == split]


def intent_agent(intent: str) -> str:
    """intent를 실제 담당 에이전트 이름으로 변환합니다."""
    return next(
        (agent for prefix, agent in INTENT_AGENT_PREFIXES.items() if intent.startswith(prefix)),
        "general",
    )


def classify_failure(expected_intent: str, actual_intent: str) -> str:
    """예상 intent와 실제 intent 차이를 개선 가능한 실패 유형으로 구분합니다."""
    if actual_intent == expected_intent:
        return "passed"
    if intent_agent(actual_intent) != intent_agent(expected_intent):
        return "wrong_agent"
    return "intent_detail_mismatch"


def evaluate_case(case: dict) -> dict:
    """DB를 변경하지 않고 Supervisor의 라우팅 결과만 평가합니다."""
    result = router_node(
        {
            "text": case["message"],
            "history": case.get("history", []),
            "service": supervisor_service,
            "user_id": 1,
        }
    )
    actual_intent = result.get("intent", "general")
    expected_intent = case["expected"]["intent"]
    expected_tasks = [task["intent"] for task in case["expected"].get("tasks", [])]
    actual_tasks = [task.get("intent") for task in result.get("tasks", []) if isinstance(task, dict)]
    return {
        "id": case["id"],
        "agent": case["agent"],
        "message": case["message"],
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "intent_passed": actual_intent == expected_intent,
        "agent_routing_passed": intent_agent(actual_intent) == intent_agent(expected_intent),
        "expected_tasks": expected_tasks,
        "actual_tasks": actual_tasks,
        "task_decomposition_passed": not expected_tasks or actual_tasks == expected_tasks,
        "failure_type": classify_failure(expected_intent, actual_intent),
    }


def build_report(results: list[dict], split: str) -> dict:
    """전체 및 도메인별 intent·에이전트 라우팅 정확도 보고서를 만듭니다."""
    grouped = defaultdict(list)
    for result in results:
        grouped[result["agent"]].append(result)

    by_agent = {
        agent: {
            "total": len(items),
            "intent_passed": sum(item["intent_passed"] for item in items),
            "intent_accuracy": round(sum(item["intent_passed"] for item in items) / len(items), 4),
            "agent_routing_passed": sum(item["agent_routing_passed"] for item in items),
            "agent_routing_accuracy": round(sum(item["agent_routing_passed"] for item in items) / len(items), 4),
        }
        for agent, items in sorted(grouped.items())
    }
    intent_passed = sum(item["intent_passed"] for item in results)
    agent_routing_passed = sum(item["agent_routing_passed"] for item in results)
    multi_intent_results = [item for item in results if item["expected_tasks"]]
    task_decomposition_passed = sum(item["task_decomposition_passed"] for item in multi_intent_results)
    return {
        "evaluated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "supervisor_routing_only",
        "split": split,
        "total": len(results),
        "intent_passed": intent_passed,
        "intent_accuracy": round(intent_passed / len(results), 4) if results else 0.0,
        "agent_routing_passed": agent_routing_passed,
        "agent_routing_accuracy": round(agent_routing_passed / len(results), 4) if results else 0.0,
        "multi_intent_total": len(multi_intent_results),
        "task_decomposition_passed": task_decomposition_passed,
        "task_decomposition_accuracy": round(task_decomposition_passed / len(multi_intent_results), 4) if multi_intent_results else 0.0,
        "by_agent": by_agent,
        "intent_failures": [item for item in results if not item["intent_passed"]],
        "agent_routing_failures": [item for item in results if not item["agent_routing_passed"]],
        "failure_summary": dict(Counter(item["failure_type"] for item in results if item["failure_type"] != "passed")),
        "actual_intents": dict(Counter(item["actual_intent"] for item in results)),
    }


def main() -> None:
    """명령행 인자를 받아 평가를 실행하고 JSON 결과를 저장합니다."""
    parser = argparse.ArgumentParser(description="Supervisor 라우팅 평가 실행기")
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="holdout")
    parser.add_argument("--limit", type=int, default=0, help="빠른 점검용 케이스 수 제한")
    parser.add_argument("--output", type=Path, help="평가 결과 JSON 저장 경로")
    args = parser.parse_args()

    cases = load_cases(args.split)
    if args.limit:
        cases = cases[: args.limit]
    results = [evaluate_case(case) for case in cases]
    report = build_report(results, args.split)

    output_path = args.output or Path("outputs/agent_evaluations/supervisor-routing.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Intent accuracy: {report['intent_passed']}/{report['total']} ({report['intent_accuracy']:.1%})")
    print(f"Agent routing accuracy: {report['agent_routing_passed']}/{report['total']} ({report['agent_routing_accuracy']:.1%})")
    if report["multi_intent_total"]:
        print(f"Task decomposition accuracy: {report['task_decomposition_passed']}/{report['multi_intent_total']} ({report['task_decomposition_accuracy']:.1%})")
    print(f"결과 파일: {output_path}")


if __name__ == "__main__":
    main()