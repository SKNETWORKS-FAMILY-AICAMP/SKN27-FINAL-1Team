"""도메인 에이전트의 실제 응답 결과를 엄격한 기준으로 평가합니다."""

import argparse
import json
from collections import defaultdict
from pathlib import Path


DATASET_PATH = Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl")


def load_jsonl(path: Path) -> list[dict]:
    """UTF-8 JSONL 파일을 빈 줄 없이 읽습니다."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def evaluate_case(case: dict, result: dict) -> dict:
    """도메인 일치, 핵심 정보, 금지 표현, 길이와 액션을 함께 검증합니다."""
    response_text = str(result.get("response_text") or result.get("message") or "")
    actions = result.get("actions") if isinstance(result.get("actions"), list) else []
    status = str(result.get("status") or (result.get("slots") or {}).get("agent_status") or "").lower()
    infrastructure_error = bool(result.get("error")) or status == "error"
    acceptance = case["expected"]["acceptance"]
    required_any = acceptance.get("must_contain_any", [])
    required_all = acceptance.get("must_contain_all", [])
    forbidden = acceptance.get("forbidden_patterns", [])
    minimum_length = int(acceptance.get("minimum_length", 20))
    actions_required = bool(acceptance.get("requires_action"))
    required_any_passed = not required_any or any(word in response_text for word in required_any)
    required_all_passed = all(word in response_text for word in required_all)
    forbidden_passed = not any(word in response_text for word in forbidden)
    action_passed = not actions_required or bool(actions)
    passed = (
        not infrastructure_error
        and len(response_text.strip()) >= minimum_length
        and required_any_passed
        and required_all_passed
        and forbidden_passed
        and action_passed
    )
    return {
        "id": case["id"],
        "agent": case["agent"],
        "passed": passed,
        "excluded": infrastructure_error,
        "response_text": response_text,
        "missing_required_any": required_any if required_any and not required_any_passed else [],
        "missing_required_all": [word for word in required_all if word not in response_text],
        "matched_forbidden": [word for word in forbidden if word in response_text],
        "too_short": bool(response_text.strip()) and len(response_text.strip()) < minimum_length,
        "missing_action": actions_required and not bool(actions),
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
        return {
            "executed": len(rows),
            "evaluated": len(eligible),
            "infrastructure_errors": len(rows) - len(eligible),
            "passed": passed,
            "accuracy": round(passed / len(eligible), 4) if eligible else None,
        }

    eligible = [row for row in evaluated if not row["excluded"]]
    passed = sum(row["passed"] for row in eligible)
    return {
        "scope": "domain_agent_response_quality",
        "executed": len(evaluated),
        "evaluated": len(eligible),
        "infrastructure_errors": len(evaluated) - len(eligible),
        "passed": passed,
        "accuracy": round(passed / len(eligible), 4) if eligible else None,
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

    report = build_report(load_jsonl(DATASET_PATH), load_jsonl(args.results))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for agent, summary in report["by_agent"].items():
        accuracy = f"{summary['accuracy']:.1%}" if summary["accuracy"] is not None else "N/A"
        print(f"{agent}: {summary['passed']}/{summary['evaluated']} ({accuracy}), infrastructure_errors={summary['infrastructure_errors']}")
    overall_accuracy = f"{report['accuracy']:.1%}" if report["accuracy"] is not None else "N/A"
    print(f"overall: {report['passed']}/{report['evaluated']} ({overall_accuracy}), infrastructure_errors={report['infrastructure_errors']}")


if __name__ == "__main__":
    main()
