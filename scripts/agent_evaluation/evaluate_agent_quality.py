"""도메인 에이전트의 실제 응답 결과를 엄격한 기준으로 평가합니다."""

import argparse
import json
from collections import defaultdict
from pathlib import Path


DATASET_PATHS = (
    Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl"),
    Path("test/fixtures/agent_evaluation/agent_regression_cases.jsonl"),
)


def load_jsonl(path: Path) -> list[dict]:
    """UTF-8 JSONL 파일을 빈 줄 없이 읽습니다."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_cases() -> list[dict]:
    """고난도 평가셋과 실제 실패 회귀셋을 함께 읽습니다."""
    return [case for path in DATASET_PATHS for case in load_jsonl(path)]


def evaluate_case(case: dict, result: dict) -> dict:
    """응답 내용, 출처, 확인 액션, 슬롯을 함께 검증합니다."""
    response_text = str(result.get("response_text") or result.get("message") or "")
    actions = result.get("actions") if isinstance(result.get("actions"), list) else []
    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    slots = result.get("slots") if isinstance(result.get("slots"), dict) else {}
    status = str(result.get("status") or (result.get("slots") or {}).get("agent_status") or "").lower()
    infrastructure_error = bool(result.get("error")) or status == "error"
    acceptance = case["expected"]["acceptance"]
    required_any = acceptance.get("must_contain_any", [])
    required_all = acceptance.get("must_contain_all", [])
    forbidden = acceptance.get("forbidden_patterns", [])
    minimum_length = int(acceptance.get("minimum_length", 20))
    actions_required = bool(acceptance.get("requires_action"))
    minimum_sources = int(acceptance.get("minimum_sources", 0))
    source_url_required = bool(acceptance.get("requires_source_url"))
    required_action_labels = acceptance.get("required_action_labels", [])
    required_slot_keys = acceptance.get("required_slot_keys", [])
    required_any_passed = not required_any or any(word in response_text for word in required_any)
    required_all_passed = all(word in response_text for word in required_all)
    forbidden_passed = not any(word in response_text for word in forbidden)
    action_passed = not actions_required or bool(actions)
    action_labels = [str(action.get("label") or "") for action in actions if isinstance(action, dict)]
    required_action_labels_passed = all(
        any(label in action_label for action_label in action_labels)
        for label in required_action_labels
    )
    source_passed = len(sources) >= minimum_sources
    source_url_passed = not source_url_required or any(
        isinstance(source, dict) and str(source.get("url") or "").startswith(("http://", "https://"))
        for source in sources
    )
    required_slots_passed = all(key in slots and slots[key] is not None for key in required_slot_keys)
    response_quality_passed = (
        not infrastructure_error
        and len(response_text.strip()) >= minimum_length
        and required_any_passed
        and required_all_passed
        and forbidden_passed
        and action_passed
    )
    structure_passed = required_action_labels_passed and required_slots_passed
    source_requirements_passed = source_passed and source_url_passed
    passed = (
        response_quality_passed
        and required_action_labels_passed
        and required_slots_passed
        and source_requirements_passed
    )
    return {
        "id": case["id"],
        "agent": case["agent"],
        "passed": passed,
        "response_quality_passed": response_quality_passed,
        "structure_passed": structure_passed,
        "source_requirements_passed": source_requirements_passed,
        "source_required": minimum_sources > 0 or source_url_required,
        "excluded": infrastructure_error,
        "response_text": response_text,
        "missing_required_any": required_any if required_any and not required_any_passed else [],
        "missing_required_all": [word for word in required_all if word not in response_text],
        "matched_forbidden": [word for word in forbidden if word in response_text],
        "too_short": bool(response_text.strip()) and len(response_text.strip()) < minimum_length,
        "missing_action": actions_required and not bool(actions),
        "missing_action_labels": [
            label
            for label in required_action_labels
            if not any(label in action_label for action_label in action_labels)
        ],
        "missing_sources": max(0, minimum_sources - len(sources)),
        "missing_source_url": source_url_required and not source_url_passed,
        "missing_slot_keys": [key for key in required_slot_keys if key not in slots or slots[key] is None],
        "error": result.get("error"),
    }


def build_report(cases: list[dict], results: list[dict]) -> dict:
    """실행된 케이스만 집계하고 인프라 오류는 품질 점수에서 분리합니다."""
    results_by_id = {row["id"]: row for row in results}
    evaluated = [evaluate_case(case, results_by_id[case["id"]]) for case in cases if case["id"] in results_by_id]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in evaluated:
        grouped[row["agent"]].append(row)

    def summary(rows: list[dict]) -> dict:
        """한 에이전트의 품질 결과를 집계합니다."""
        eligible = [row for row in rows if not row["excluded"]]
        passed = sum(row["passed"] for row in eligible)
        response_quality_passed = sum(row["response_quality_passed"] for row in eligible)
        structure_passed = sum(row["structure_passed"] for row in eligible)
        source_required = [row for row in eligible if row["source_required"]]
        source_requirements_passed = sum(row["source_requirements_passed"] for row in source_required)
        return {
            "executed": len(rows),
            "evaluated": len(eligible),
            "infrastructure_errors": len(rows) - len(eligible),
            "passed": passed,
            "accuracy": round(passed / len(eligible), 4) if eligible else None,
            "response_quality_passed": response_quality_passed,
            "response_quality_accuracy": round(response_quality_passed / len(eligible), 4) if eligible else None,
            "structure_passed": structure_passed,
            "structure_accuracy": round(structure_passed / len(eligible), 4) if eligible else None,
            "source_required": len(source_required),
            "source_requirements_passed": source_requirements_passed,
            "source_coverage": round(source_requirements_passed / len(source_required), 4) if source_required else None,
        }

    eligible = [row for row in evaluated if not row["excluded"]]
    passed = sum(row["passed"] for row in eligible)
    response_quality_passed = sum(row["response_quality_passed"] for row in eligible)
    return {
        "scope": "domain_agent_response_quality",
        "executed": len(evaluated),
        "evaluated": len(eligible),
        "infrastructure_errors": len(evaluated) - len(eligible),
        "passed": passed,
        "accuracy": round(passed / len(eligible), 4) if eligible else None,
        "response_quality_accuracy": round(response_quality_passed / len(eligible), 4) if eligible else None,
        "by_agent": {agent: summary(rows) for agent, rows in sorted(grouped.items())},
        "failures": [row for row in eligible if not row["passed"]],
        "infrastructure_failure_details": [row for row in evaluated if row["excluded"]],
    }


def main() -> None:
    """실행 결과 JSONL로 에이전트별 품질 보고서를 생성합니다."""
    parser = argparse.ArgumentParser(description="도메인 에이전트 응답 품질 평가")
    parser.add_argument("--results", required=True, type=Path, help="id와 response_text를 가진 실행 결과 JSONL")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/domain-agent-quality.json"))
    args = parser.parse_args()

    report = build_report(load_cases(), load_jsonl(args.results))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for agent, summary in report["by_agent"].items():
        strict_accuracy = f"{summary['accuracy']:.1%}" if summary["accuracy"] is not None else "N/A"
        response_accuracy = (
            f"{summary['response_quality_accuracy']:.1%}"
            if summary["response_quality_accuracy"] is not None
            else "N/A"
        )
        source_coverage = f"{summary['source_coverage']:.1%}" if summary["source_coverage"] is not None else "N/A"
        print(
            f"{agent}: strict={summary['passed']}/{summary['evaluated']} ({strict_accuracy}), "
            f"response={response_accuracy}, source_coverage={source_coverage}, "
            f"infrastructure_errors={summary['infrastructure_errors']}"
        )
    overall_accuracy = f"{report['accuracy']:.1%}" if report["accuracy"] is not None else "N/A"
    print(f"overall: {report['passed']}/{report['evaluated']} ({overall_accuracy}), infrastructure_errors={report['infrastructure_errors']}")


if __name__ == "__main__":
    main()
